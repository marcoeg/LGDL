import uuid
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from ..parser.parser import parse_lgdl
from ..parser.ir import compile_game, extract_capability_allowlist
from .matcher import TwoStageMatcher, CascadeMatcher
from .matching_context import MatchingContext
from .firewall import sanitize
from .policy import PolicyGuard
from .capability import CapabilityClient
from .templates import TemplateRenderer
from .negotiation import NegotiationLoop, NegotiationResult
from .state import StateManager, Turn
from .context import ContextEnricher
from .response_parser import ResponseParser
from .slots import SlotManager
from ..errors import RuntimeError as LGDLRuntimeError
from ..config import LGDLConfig
from ..metrics import get_global_metrics

def eval_condition(cond: Dict[str, Any], score: float, threshold: float, last_status: str, ctx: Dict[str, Any]) -> bool:
    if not cond:
        return False
    if "special" in cond:
        if cond["special"] == "confident":
            return score >= threshold
        if cond["special"] == "uncertain":
            return score < threshold
        if cond["special"] == "successful":
            return last_status == "ok"
        if cond["special"] == "failed":
            return last_status == "err"
        # Slot conditions are handled in slot-filling code, not here
        if cond["special"] == "slot_missing":
            return False
        if cond["special"] == "all_slots_filled":
            return False
    if "op" in cond and cond["op"] in ("and","or"):
        a = eval_condition(cond["left"], score, threshold, last_status, ctx)
        b = eval_condition(cond["right"], score, threshold, last_status, ctx)
        return (a and b) if cond["op"] == "and" else (a or b)
    if "cmp" in cond:
        lhs = ctx.get(cond["lhs"]["ref"], None) if isinstance(cond["lhs"], dict) and "ref" in cond["lhs"] else None
        rhs = cond["rhs"]
        cmp = cond["cmp"]
        try:
            if cmp == "=": return lhs == rhs
            if cmp == "!=": return lhs != rhs
            if cmp == ">": return lhs > rhs
            if cmp == "<": return lhs < rhs
            if cmp == ">=": return lhs >= rhs
            if cmp == "<=": return lhs <= rhs
        except Exception:
            return False
    if "ref" in cond:
        return bool(ctx.get(cond["ref"]))
    if "not" in cond:
        return not eval_condition(cond["not"], score, threshold, last_status, ctx)
    return False

class LGDLRuntime:
    def __init__(
        self,
        compiled: Dict[str, Any],
        allowlist: Optional[Set[str]] = None,
        capability_contract_path: Optional[str] = None,
        state_manager: Optional[StateManager] = None,
        config: Optional[LGDLConfig] = None
    ):
        """
        Initialize LGDL runtime with per-game configuration.

        Args:
            compiled: Compiled game IR (output of compile_game)
            allowlist: Set of allowed capability functions. If None, auto-extracted from IR.
            capability_contract_path: Path to capability_contract.json. If None, capabilities disabled.
            state_manager: StateManager for multi-turn conversations. If None, conversations are stateless.
            config: LGDLConfig for feature flags and settings. If None, loads from environment.

        Note:
            Backward compatible: If config not provided, loads from environment with
            all new features disabled by default.
        """
        self.compiled = compiled
        self.config = config or LGDLConfig.from_env()

        # Phase 1: Config-based matcher selection
        print(f"[Runtime] Initializing LGDL runtime for game: {compiled.get('name', 'unknown')}")

        if self.config.enable_llm_semantic_matching:
            # Use cascade matcher with LLM semantic stage
            # This will raise ValueError if no API key (explicit failure)
            print(f"[Runtime] LLM semantic matching: ENABLED")
            self.matcher = CascadeMatcher(self.config)
            self.use_cascade = True
        else:
            # Backward compatible: Use existing two-stage matcher
            print(f"[Runtime] LLM semantic matching: DISABLED (using TwoStageMatcher)")
            self.matcher = TwoStageMatcher()
            self.use_cascade = False

        # Auto-extract allowlist from IR if not provided
        if allowlist is None:
            allowlist = extract_capability_allowlist(compiled)

        self.policy = PolicyGuard(allowlist=allowlist)

        # Only create CapabilityClient if contract path provided
        if capability_contract_path:
            self.cap = CapabilityClient(capability_contract_path)
        else:
            self.cap = None

        self.templates = TemplateRenderer()
        self.negotiation = NegotiationLoop(
            max_rounds=int(os.getenv("LGDL_NEGOTIATION_MAX_ROUNDS", "3")),
            epsilon=float(os.getenv("LGDL_NEGOTIATION_EPSILON", "0.05"))
        )
        self.negotiation_enabled = os.getenv("LGDL_NEGOTIATION", "1") == "1"

        # State management for multi-turn conversations
        self.state_manager = state_manager
        self.context_enricher = ContextEnricher() if state_manager else None
        self.response_parser = ResponseParser() if state_manager else None
        # Phase 2: Pass config to SlotManager for extraction strategies
        self.slot_manager = SlotManager(state_manager, self.config) if state_manager else None

    async def process_turn(self, conversation_id: str, user_id: str, text: str, context: Dict[str, Any]):
        # Load conversation state if state management is enabled
        state = None
        if self.state_manager:
            state = await self.state_manager.get_or_create(conversation_id)

        # Sanitize input
        cleaned, flagged = sanitize(text)

        # Apply context enrichment if state management is enabled
        input_for_matching = cleaned
        if self.state_manager and self.context_enricher and state:
            enriched_result = self.context_enricher.enrich_input(cleaned, state)
            if enriched_result.enrichment_applied:
                input_for_matching = enriched_result.enriched_input
                print(f"[Context] Enriched: '{cleaned}' → '{input_for_matching}'")

        # Check if we're awaiting a slot - if so, route directly to that move
        mv = None
        score = 0.0
        params = {}

        if state and state.awaiting_slot_for_move:
            # We're in the middle of slot-filling - route to the awaiting move
            awaiting_move_id = state.awaiting_slot_for_move
            mv = next((m for m in self.compiled["moves"] if m["id"] == awaiting_move_id), None)
            if mv:
                score = 1.0  # Direct route, high confidence
                params = {}  # Empty params, will fill from user input
                print(f"[Slot] Routing to awaiting move: {awaiting_move_id}")
            else:
                # Move not found, clear state and proceed with normal matching
                state.awaiting_slot_for_move = None
                state.awaiting_slot_name = None

        # If not awaiting slot, match against moves using potentially enriched input
        if not mv:
            # Phase 1: Build matching context for cascade (if enabled)
            matching_context = None
            start_time = time.time()

            if self.use_cascade:
                # Build rich context for LLM semantic matching
                matching_context = MatchingContext.from_state(self.compiled, state)

            # Match with context (cascade uses it, two-stage ignores it)
            if self.use_cascade:
                match = await self.matcher.match(input_for_matching, self.compiled, matching_context)
            else:
                match = self.matcher.match(input_for_matching, self.compiled)

            # Track metrics
            latency_ms = (time.time() - start_time) * 1000
            match_stage = match.get("stage", "unknown")
            match_cost = match.get("cost", 0.0) if self.use_cascade else 0.0

            # Record in global metrics
            if match["move"]:
                get_global_metrics().record_turn(
                    stage=match_stage,
                    confidence=match["score"],
                    latency_ms=latency_ms,
                    cost_usd=match_cost
                )

            if not match["move"]:
                return {
                    "move_id": "none",
                    "confidence": 0.0,
                    "response": "Sorry, I didn't catch that.",
                    "action": None,
                    "manifest_id": str(uuid.uuid4()),
                    "firewall_triggered": flagged,
                    "stage": match_stage
                }
            mv = match["move"]
            score = match["score"]
            params = match["params"]
        threshold = mv["threshold"]
        last_status = "ok"

        # NEW: Negotiation trigger
        negotiation_result = None
        if self.negotiation_enabled and score < threshold and self._has_clarify(mv):
            try:
                negotiation_result = await self.negotiation.clarify_until_confident(
                    mv, cleaned, match, self.matcher, self.compiled,
                    ask_user=lambda q, opts: self._prompt_user(conversation_id, q, opts)
                )

                # Log to stdout (no PII, just metrics)
                for r in negotiation_result.rounds:
                    delta = r.confidence_after - r.confidence_before
                    print(
                        f"[Negotiation R{r.round_num}] "
                        f"{r.confidence_before:.2f} → {r.confidence_after:.2f} "
                        f"(Δ{delta:+.2f})"
                    )

                if negotiation_result.success:
                    # Update for execution
                    score = negotiation_result.final_confidence
                    params = negotiation_result.final_params
                    print(f"[Negotiation] ✓ {negotiation_result.reason}")
                else:
                    # Early return with failure
                    print(f"[Negotiation] ✗ {negotiation_result.reason}")
                    return {
                        "move_id": mv["id"],
                        "confidence": negotiation_result.final_confidence,
                        "response": (
                            f"I wasn't able to understand after "
                            f"{len(negotiation_result.rounds)} clarifications."
                        ),
                        "negotiation": self._negotiation_to_manifest(negotiation_result),
                        "manifest_id": str(uuid.uuid4()),
                        "firewall_triggered": flagged
                    }
            except LGDLRuntimeError as e:
                # E200 errors: log and skip negotiation
                print(f"[Negotiation] Skipped: {e.message} ({e.code})")

        # Initialize response accumulators (used by both slot and non-slot moves)
        response_acc = ""
        action_out = None
        last_status = "ok"

        # NEW: Slot-filling logic for multi-turn information gathering
        if "slots" in mv and self.slot_manager and state:
            # Determine if we're responding to a specific slot prompt
            awaiting_specific_slot = state.awaiting_slot_name if state.awaiting_slot_for_move == mv["id"] else None

            # Phase 2: Build rich context for semantic extraction
            extraction_context = {
                "conversation_history": state.history[-5:] if state and hasattr(state, "history") else [],
                "filled_slots": await self.slot_manager.get_slot_values(mv["id"], conversation_id),
                "current_move": mv["id"]
            }

            # Try to extract slot values from current input
            for slot_name, slot_def in mv["slots"].items():
                # Check if slot already filled
                if not await self.slot_manager.has_slot(conversation_id, mv["id"], slot_name):
                    value = None

                    # Priority 1: Pattern-captured params
                    if slot_name in params and params[slot_name] is not None:
                        value = params[slot_name]
                        print(f"[Slot] Extracted '{slot_name}' from pattern: {value}")

                    # Priority 2: If we're awaiting THIS specific slot, extract from input
                    elif awaiting_specific_slot == slot_name:
                        # Phase 2: Pass full slot_def and context (now async)
                        value = await self.slot_manager.extract_slot_from_input(
                            cleaned,
                            slot_def,  # Full definition with extraction_strategy, vocabulary
                            extraction_context
                        )
                        if value:
                            print(f"[Slot] Extracted '{slot_name}' from awaiting input: {value}")

                    # Don't extract from input for other slots - wait for their turn

                    if value is not None:
                        # Validate the value
                        is_valid, coerced = self.slot_manager.validate_slot_value(slot_def, value)
                        if is_valid:
                            await self.slot_manager.fill_slot(conversation_id, mv["id"], slot_name, coerced, slot_def["type"])
                            print(f"[Slot] Filled '{slot_name}' = {coerced}")
                        else:
                            print(f"[Slot] Validation failed for '{slot_name}': {value}")

            # Check if all required slots are filled
            if not await self.slot_manager.all_required_filled(mv, conversation_id):
                # Get the first missing slot and prompt for it
                missing = await self.slot_manager.get_missing_slots(mv, conversation_id)
                if missing:
                    slot_name = missing[0]
                    # Get the prompt from IR
                    prompt = mv.get("slot_prompts", {}).get(slot_name, f"Please provide {slot_name}")

                    print(f"[Slot] Missing required slot '{slot_name}', prompting user")

                    # Set awaiting state so next input routes back to this move
                    if state:
                        state.awaiting_slot_for_move = mv["id"]
                        state.awaiting_slot_name = slot_name
                        await self.state_manager.persistent_storage.save_conversation(state)

                    return {
                        "move_id": mv["id"],
                        "confidence": float(score),
                        "response": prompt,
                        "action": None,
                        "awaiting_slot": slot_name,
                        "manifest_id": str(uuid.uuid4()),
                        "firewall_triggered": flagged
                    }

            # All required slots filled - get slot values and add to params
            slot_values = await self.slot_manager.get_slot_values(mv["id"], conversation_id)
            params.update(slot_values)
            print(f"[Slot] All slots filled: {slot_values}")

            # Clear awaiting state since all slots are filled
            if state:
                state.awaiting_slot_for_move = None
                state.awaiting_slot_name = None

            # Execute all_slots_filled actions if defined
            if "all_slots_filled" in mv.get("slot_conditions", {}):
                # Execute all_slots_filled actions first
                for action in mv["slot_conditions"]["all_slots_filled"]:
                    r, action_out, last_status = await self._exec_action(action, params)
                    if r:
                        response_acc += ("" if not response_acc else " ") + r

                # Clear slots after execution
                await self.slot_manager.clear_slots(conversation_id, mv["id"])

                # DON'T return here - continue to normal blocks
                # so "when successful" / "when failed" can trigger

        # Normal block execution (continues from slot-filling or starts fresh for non-slot moves)
        branch_executed = False

        for blk in mv["blocks"]:
            if branch_executed:
                break  # SINGLE-BRANCH GUARANTEE

            # Debug: log block evaluation
            cond = blk.get("condition", {})
            cond_str = cond.get("special", str(cond)[:50])
            print(f"[Block] Checking condition: {cond_str}, last_status={last_status}")

            if blk["kind"] == "if_chain":
                for link in blk["chain"]:
                    cond = link["condition"]
                    if eval_condition(cond, score, threshold, last_status, params):
                        for act in link["actions"]:
                            r, action_out, last_status = await self._exec_action(act, params)
                            if r:
                                response_acc += ("" if not response_acc else " ") + r
                        branch_executed = True
                        break
                continue

            cond = blk.get("condition")
            eval_result = eval_condition(cond, score, threshold, last_status, params)
            print(f"[Block] Condition '{cond_str}' evaluated to: {eval_result}")

            if eval_result:
                print(f"[Block] Executing block with {len(blk.get('actions', []))} actions")
                for act in blk.get("actions", []):
                    r, action_out, last_status = await self._exec_action(act, params)
                    if r:
                        response_acc += ("" if not response_acc else " ") + r
                        print(f"[Block] Added response: {r[:80]}...")
                branch_executed = True

        if not response_acc:
            response_acc = "OK."

        # Build result with negotiation metadata if present
        result = {
            "move_id": mv["id"],
            "confidence": float(score),
            "response": response_acc,
            "action": action_out,
            "manifest_id": str(uuid.uuid4()),
            "firewall_triggered": flagged
        }

        # Phase 1: Add cascade stage metadata
        if self.use_cascade:
            result["stage"] = match_stage
            if match.get("reasoning"):
                result["reasoning"] = match.get("reasoning")
            if match.get("provenance"):
                result["provenance"] = match.get("provenance")

        if negotiation_result:
            result["negotiation"] = self._negotiation_to_manifest(negotiation_result)

        # Store turn in conversation history if state management is enabled
        if self.state_manager and state:
            turn = Turn(
                turn_num=state.turn_count + 1,
                timestamp=datetime.utcnow(),
                user_input=text,
                sanitized_input=cleaned,
                matched_move=mv["id"],
                confidence=float(score),
                response=response_acc,
                extracted_params=params
            )
            updated_state = await self.state_manager.update(conversation_id, turn, extracted_params=params)

            # Parse response for questions AFTER storing turn (critical for context enrichment)
            if self.response_parser:
                parsed_response = self.response_parser.parse_response(response_acc)

                # Update conversation state with question tracking
                if parsed_response.has_questions:
                    updated_state.awaiting_response = True
                    updated_state.last_question = parsed_response.primary_question
                    print(f"[Question Detected] Awaiting response to: {updated_state.last_question}")
                else:
                    updated_state.awaiting_response = False
                    updated_state.last_question = None

                # Save the updated state back to database
                await self.state_manager.persistent_storage.save_conversation(updated_state)
                # Update cache
                await self.state_manager.ephemeral_cache.set(f"persistent:{conversation_id}", updated_state)

        return result

    async def _exec_action(self, action: Dict[str, Any], params: Dict[str, Any]):
        atype = action.get("type")
        data = action.get("data", {})
        status = "ok"
        if atype == "respond":
            return self.templates.render(data.get("text",""), params), None, status
        if atype == "offer_choices":
            return "Options: " + ", ".join(data.get("choices", [])), None, status
        if atype == "capability":
            call = data.get("call", {})
            func = call.get("function")
            if not self.policy.allowed(func):
                return "Not allowed.", None, "err"
            # Check if capabilities are enabled
            if not self.cap:
                return "Capabilities not configured.", None, "err"
            # Build payload from all non-None params (generalized for all games)
            payload = {}
            for k, v in params.items():
                if v is not None and not k.startswith("_"):
                    payload[k] = v
            res = await self.cap.execute(f'{call.get("service")}.{func}', payload)

            # Merge response data into params for subsequent template rendering
            # This enables templates to use values like ${base_price * quantity}
            if "data" in res and isinstance(res["data"], dict):
                params.update(res["data"])

            return res.get("message",""), func, status
        if atype in ("continue","return"):
            return "", None, status
        if atype == "escalate":
            return "Escalating to " + data.get("to","human"), "escalate", status
        return "", None, status

    def _has_clarify(self, move: dict) -> bool:
        """
        Check if move has clarify action in uncertain block.

        Args:
            move: Move IR

        Returns:
            True if move has ask_clarification/clarify action in uncertain block
        """
        for block in move.get("blocks", []):
            if block.get("condition", {}).get("special") == "uncertain":
                for action in block.get("actions", []):
                    if action.get("type") in ("ask_clarification", "clarify"):
                        return True
        return False

    async def _prompt_user(self, conversation_id: str, question: str, options: List[str]) -> str:
        """
        Prompt user for clarification during negotiation.

        IMPORTANT: This method cannot be fully implemented in v1.0-beta because
        the current request/response model doesn't support mid-request user interaction.

        Full implementation requires one of:
        - WebSocket connection for real-time bidirectional communication
        - Async message queue (Redis pub/sub, RabbitMQ, etc.)
        - Polling mechanism with session state

        Current behavior:
        - In TEST_MODE (env LGDL_TEST_MODE=1): Auto-selects first option
        - Otherwise: Marks conversation as awaiting_response and raises NotImplementedError

        Args:
            conversation_id: Conversation identifier
            question: Clarification question to ask user
            options: List of suggested options (if available)

        Returns:
            User's response (in test mode, returns first option)

        Raises:
            NotImplementedError: In production mode (requires async infrastructure)

        Example production integration:
            ```python
            # Publish question to message queue
            await self.message_queue.publish(conversation_id, {
                "type": "clarification_request",
                "question": question,
                "options": options
            })

            # Wait for user response (with timeout)
            response = await self.message_queue.wait_for_response(
                conversation_id,
                timeout=30.0
            )

            return response["text"]
            ```

        For testing, use unittest.mock.patch:
            ```python
            with patch.object(engine, '_prompt_user', return_value="option1"):
                result = await engine.process(...)
            ```
        """
        import os

        # Mark conversation as awaiting response if state management enabled
        if self.state_manager:
            await self.state_manager.set_awaiting_response(conversation_id, question)
            print(f"[Negotiation] Awaiting user response to: {question}")
            if options:
                print(f"[Negotiation] Options: {', '.join(options)}")

        # Test mode: auto-select first option for automated testing
        test_mode = os.getenv("LGDL_TEST_MODE", "0") == "1"
        if test_mode and options:
            selected = options[0]
            print(f"[Negotiation] TEST_MODE: Auto-selected '{selected}'")
            return selected

        # Production mode: requires async messaging infrastructure
        raise NotImplementedError(
            "User prompting requires async messaging infrastructure (WebSocket, "
            "message queue, or polling). Set LGDL_TEST_MODE=1 to auto-select first "
            "option for testing, or mock this method with unittest.mock.patch."
        )

    def _negotiation_to_manifest(self, result: NegotiationResult) -> dict:
        """
        Convert NegotiationResult to stable manifest format.

        Args:
            result: NegotiationResult from clarify_until_confident

        Returns:
            Dictionary with structured negotiation metadata
        """
        return {
            "enabled": True,
            "rounds": [
                {
                    "n": r.round_num,
                    "q": r.question,
                    "a": r.user_response,
                    "before": round(r.confidence_before, 3),
                    "after": round(r.confidence_after, 3),
                    "delta": round(r.confidence_after - r.confidence_before, 3)
                }
                for r in result.rounds
            ],
            "final_confidence": round(result.final_confidence, 3),
            "reason": result.reason
        }

def load_compiled_game(path: str):
    game = parse_lgdl(path)
    return compile_game(game)

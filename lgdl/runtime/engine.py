import uuid
import os
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from ..parser.parser import parse_lgdl
from ..parser.ir import compile_game, extract_capability_allowlist
from .matcher import TwoStageMatcher
from .firewall import sanitize
from .policy import PolicyGuard
from .capability import CapabilityClient
from .templates import TemplateRenderer
from .negotiation import NegotiationLoop, NegotiationResult
from ..errors import RuntimeError as LGDLRuntimeError

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
        capability_contract_path: Optional[str] = None
    ):
        """
        Initialize LGDL runtime with per-game configuration.

        Args:
            compiled: Compiled game IR (output of compile_game)
            allowlist: Set of allowed capability functions. If None, auto-extracted from IR.
            capability_contract_path: Path to capability_contract.json. If None, capabilities disabled.

        Note:
            Backward compatible: If allowlist/capability_contract_path not provided,
            falls back to extracting allowlist from IR and disabling capabilities.
        """
        self.compiled = compiled
        self.matcher = TwoStageMatcher()

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

    async def process_turn(self, conversation_id: str, user_id: str, text: str, context: Dict[str, Any]):
        cleaned, flagged = sanitize(text)
        match = self.matcher.match(cleaned, self.compiled)
        if not match["move"]:
            return {
                "move_id": "none",
                "confidence": 0.0,
                "response": "Sorry, I didn't catch that.",
                "action": None,
                "manifest_id": str(uuid.uuid4()),
                "firewall_triggered": flagged
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

        response_acc = ""
        action_out = None
        branch_executed = False

        for blk in mv["blocks"]:
            if branch_executed:
                break  # SINGLE-BRANCH GUARANTEE
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
            if eval_condition(cond, score, threshold, last_status, params):
                for act in blk.get("actions", []):
                    r, action_out, last_status = await self._exec_action(act, params)
                    if r:
                        response_acc += ("" if not response_acc else " ") + r
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

        if negotiation_result:
            result["negotiation"] = self._negotiation_to_manifest(negotiation_result)

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
        Stub for user prompting (not implemented in MVP).

        In production, this would send message via async channel and await response.
        For tests, mock this method using unittest.mock.patch.

        Args:
            conversation_id: Conversation identifier
            question: Clarification question
            options: List of suggested options

        Returns:
            User's response

        Raises:
            NotImplementedError: Always (stub implementation)
        """
        raise NotImplementedError(
            "User prompting not implemented in MVP. "
            "Mock this method in tests with unittest.mock.patch."
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

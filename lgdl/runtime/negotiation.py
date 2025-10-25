"""
Negotiation state management for clarification loops.

Handles multi-round clarification when confidence is below threshold,
with three stop conditions:
1. Confidence crosses threshold (success)
2. Maximum rounds reached (timeout)
3. No confidence gain for 2 consecutive rounds (stagnation)

Copyright (c) 2025 Graziano Labs Corp.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Callable
from ..errors import RuntimeError as LGDLRuntimeError


@dataclass
class NegotiationState:
    """
    Tracks negotiation/clarification loop progress.

    Attributes:
        round: Current round number (0 = initial, 1+ = clarification rounds)
        history: List of user inputs and assistant clarifications
        deltas: Confidence changes per round (for detecting stagnation)
        terminated: Whether negotiation has ended
        reason: Why negotiation ended (None if still active)
    """
    round: int = 0
    history: List[Dict[str, str]] = field(default_factory=list)
    deltas: List[float] = field(default_factory=list)
    terminated: bool = False
    reason: str | None = None

    def add_turn(self, role: str, content: str, confidence: float):
        """
        Record a turn in the negotiation.

        Args:
            role: "user" or "assistant"
            content: Text content of turn
            confidence: Current confidence score
        """
        self.history.append({
            "role": role,
            "content": content,
            "confidence": confidence
        })

        # Calculate delta if not first turn
        if len(self.history) > 1:
            prev_confidence = self.history[-2]["confidence"]
            delta = confidence - prev_confidence
            self.deltas.append(delta)

    def should_stop(
        self,
        confidence: float,
        threshold: float,
        max_rounds: int = 3,
        stagnation_epsilon: float = 0.05
    ) -> tuple[bool, str | None]:
        """
        Check if negotiation should stop.

        Args:
            confidence: Current confidence score
            threshold: Target confidence threshold
            max_rounds: Maximum clarification rounds allowed
            stagnation_epsilon: Minimum delta to consider progress

        Returns:
            (should_stop, reason) where reason is:
            - "threshold_met": Confidence crossed threshold
            - "max_rounds": Hit maximum rounds
            - "stagnation": No progress for 2 consecutive rounds
            - None: Continue negotiation
        """
        # Stop condition 1: Confidence crosses threshold
        if confidence >= threshold:
            return True, "threshold_met"

        # Stop condition 2: Maximum rounds reached
        if self.round >= max_rounds:
            return True, "max_rounds"

        # Stop condition 3: Stagnation (2 consecutive low deltas)
        if len(self.deltas) >= 2:
            recent_deltas = self.deltas[-2:]
            if all(abs(delta) < stagnation_epsilon for delta in recent_deltas):
                return True, "stagnation"

        return False, None

    def to_manifest(self) -> Dict[str, Any]:
        """
        Convert to manifest format for per-turn logging.

        Returns:
            Dictionary with negotiation metadata
        """
        return {
            "rounds": self.round,
            "final_confidence": self.history[-1]["confidence"] if self.history else 0.0,
            "stopped_reason": self.reason,
            "history": self.history,
            "deltas": self.deltas
        }


@dataclass
class NegotiationRound:
    """
    Record of one negotiation round.

    Attributes:
        round_num: Round number (1-indexed)
        question: Clarification question asked
        user_response: User's response to clarification
        updated_params: Parameters dict after update
        confidence_before: Confidence before this round (∈ [0,1])
        confidence_after: Confidence after this round (∈ [0,1])
        feature_deltas: Feature contribution changes (for provenance)
    """
    round_num: int
    question: str
    user_response: str
    updated_params: Dict[str, Any]
    confidence_before: float
    confidence_after: float
    feature_deltas: Dict[str, float] = field(default_factory=dict)


@dataclass
class NegotiationResult:
    """
    Final result of negotiation loop.

    Attributes:
        success: True if threshold met, False if failed
        rounds: List of NegotiationRound records
        final_confidence: Final confidence score (∈ [0,1])
        final_params: Final parameters dict
        reason: Why negotiation ended (threshold_met | max_rounds_exceeded | no_information_gain)
    """
    success: bool
    rounds: List[NegotiationRound]
    final_confidence: float
    final_params: Dict[str, Any]
    reason: str


class NegotiationLoop:
    """
    Implements clarification loop with confidence re-evaluation.

    Stop conditions (checked in order):
    1. Confidence >= threshold → success
    2. Reached max_rounds → failure
    3. No information gain (Δconf < epsilon for 2 consecutive rounds) → failure
    """

    def __init__(self, max_rounds: int = 3, epsilon: float = 0.05):
        """
        Initialize negotiation loop.

        Args:
            max_rounds: Maximum clarification rounds (default: 3)
            epsilon: Minimum confidence gain per round (default: 0.05)
        """
        self.max_rounds = max_rounds
        self.epsilon = epsilon

    async def clarify_until_confident(
        self,
        move: dict,
        initial_input: str,
        initial_match: dict,
        matcher,
        compiled_game: dict,
        ask_user: Callable[[str, List[str]], str]
    ) -> NegotiationResult:
        """
        Execute negotiation loop.

        Args:
            move: Move IR with clarify action
            initial_input: Original user input
            initial_match: Initial match result from matcher
            matcher: TwoStageMatcher instance for re-matching
            compiled_game: Compiled game IR
            ask_user: Async function to prompt user (question, options) -> response

        Returns:
            NegotiationResult with success status and metadata

        Raises:
            LGDLRuntimeError: If no clarify action found (E200)
        """
        state = NegotiationState()
        rounds = []
        params = initial_match["params"].copy()
        confidence = initial_match["score"]
        threshold = move["threshold"]
        no_gain_count = 0  # Track consecutive rounds with no gain

        for round_num in range(1, self.max_rounds + 1):
            state.round = round_num

            # Extract clarification action from move
            clarify_action = self._find_clarify_action(move)
            if not clarify_action:
                raise LGDLRuntimeError(
                    code="E200",
                    message=f"Negotiation requested but no clarify action found in move '{move['id']}'",
                    hint="Add 'if uncertain {{ ask for clarification: \"...\" }}' block to move"
                )

            question = clarify_action.get("question", "Can you clarify?")
            options = clarify_action.get("options", [])
            param_name = clarify_action.get("param_name")

            # Ask user
            user_response = await ask_user(question, options)
            state.history.append((question, user_response))

            # Record confidence before update
            confidence_before = confidence

            # Update parameters
            if param_name:
                params[param_name] = user_response

            # Reconstruct enriched input
            enriched_input = self._enrich_input(initial_input, params)

            # Re-run matcher on enriched input
            new_match = matcher.match(enriched_input, compiled_game)
            confidence_after = new_match["score"]

            # Calculate feature deltas (if provenance available)
            feature_deltas = {}
            if "provenance" in new_match:
                # TODO: Extract feature contributions from provenance
                pass

            # Record round
            rounds.append(NegotiationRound(
                round_num=round_num,
                question=question,
                user_response=user_response,
                updated_params=params.copy(),
                confidence_before=confidence_before,
                confidence_after=confidence_after,
                feature_deltas=feature_deltas
            ))

            confidence = confidence_after

            # STOP CONDITION 1: Threshold met
            if confidence >= threshold:
                return NegotiationResult(
                    success=True,
                    rounds=rounds,
                    final_confidence=confidence,
                    final_params=params,
                    reason="threshold_met"
                )

            # Track delta for stagnation detection
            delta = confidence_after - confidence_before

            # Negative delta = harmful info, reset stagnation counter
            if delta < 0:
                no_gain_count = 0
            # Tiny positive delta = no meaningful gain
            elif delta < self.epsilon:
                no_gain_count += 1
                # STOP CONDITION 3: Stagnation (2 consecutive low deltas)
                if no_gain_count >= 2:
                    return NegotiationResult(
                        success=False,
                        rounds=rounds,
                        final_confidence=confidence,
                        final_params=params,
                        reason="no_information_gain"
                    )
            # Meaningful gain, reset counter
            else:
                no_gain_count = 0

        # STOP CONDITION 2: Max rounds exceeded
        return NegotiationResult(
            success=False,
            rounds=rounds,
            final_confidence=confidence,
            final_params=params,
            reason="max_rounds_exceeded"
        )

    def _find_clarify_action(self, move: dict) -> dict | None:
        """
        Extract clarify action from uncertain block.

        Args:
            move: Move IR

        Returns:
            Clarify action data dict or None
        """
        for block in move.get("blocks", []):
            if block.get("condition", {}).get("special") == "uncertain":
                for action in block.get("actions", []):
                    if action.get("type") in ("ask_clarification", "clarify"):
                        return action.get("data", {})
        return None

    def _enrich_input(self, original: str, params: Dict[str, Any]) -> str:
        """
        Reconstruct input with extracted parameters.

        Strategy: Append new information to original input.
        Safeguards:
        - No duplicate appends (track in set)
        - Whitespace normalization
        - Length cap (2KB max)

        Example:
            original = "I need to see a doctor"
            params = {"doctor": "Smith"}
            enriched = "I need to see a doctor Smith"

        Args:
            original: Original user input
            params: Extracted/updated parameters

        Returns:
            Enriched input string
        """
        MAX_ENRICHED_LENGTH = 2048
        enriched = original
        appended = set()

        for key, val in params.items():
            if not val:
                continue
            val_str = str(val)
            val_lower = val_str.lower()

            # Skip if already in original or already appended
            if val_lower in original.lower() or val_lower in appended:
                continue

            enriched += f" {val_str}"
            appended.add(val_lower)

            # Length cap
            if len(enriched) > MAX_ENRICHED_LENGTH:
                break

        # Normalize whitespace
        enriched = " ".join(enriched.split())
        return enriched


class NegotiationManager:
    """
    Manages negotiation loops during move processing.

    TODO: Integrate with LGDLRuntime.process_turn()
    - Detect low confidence
    - Instantiate NegotiationState
    - Run clarification loop
    - Re-match with updated context
    - Record in manifest
    """

    def __init__(self, max_rounds: int = 3, stagnation_epsilon: float = 0.05):
        """
        Initialize negotiation manager.

        Args:
            max_rounds: Maximum clarification rounds
            stagnation_epsilon: Minimum delta to consider progress
        """
        self.max_rounds = max_rounds
        self.stagnation_epsilon = stagnation_epsilon

    async def negotiate(
        self,
        initial_input: str,
        initial_confidence: float,
        threshold: float,
        matcher,  # TwoStageMatcher instance
        compiled_game: Dict[str, Any],
        context: Dict[str, Any]
    ) -> tuple[Dict[str, Any], NegotiationState]:
        """
        Run negotiation loop to improve confidence.

        Args:
            initial_input: User's initial input
            initial_confidence: Initial match confidence
            threshold: Target threshold
            matcher: Matcher instance for re-matching
            compiled_game: Compiled game IR
            context: Current context (will be updated with clarifications)

        Returns:
            (final_match_result, negotiation_state)

        TODO:
        - Implement clarification question generation
        - Integrate with move blocks (ask actions)
        - Update context with user responses
        - Re-run matcher with updated context
        - Track confidence progression
        """
        state = NegotiationState()
        state.add_turn("user", initial_input, initial_confidence)

        # TODO: Implement negotiation loop logic
        # For now, return initial match and empty state
        raise NotImplementedError(
            "Negotiation loop not yet implemented. "
            "See docs/P0_P1_CRITICAL_FIXES.md section P1-1 for implementation plan."
        )

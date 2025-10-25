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
from typing import Dict, Any, List


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

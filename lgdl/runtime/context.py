"""
Context enrichment for multi-turn conversations.

Enriches current user input with conversation history to enable
natural follow-up responses and context-aware pattern matching.

Copyright (c) 2025 Graziano Labs Corp.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import logging

from .state import PersistentState, Turn

logger = logging.getLogger(__name__)


@dataclass
class EnrichedInput:
    """User input enriched with conversation context"""
    original_input: str
    enriched_input: str
    context_used: Dict[str, Any]
    enrichment_applied: bool


class ContextEnricher:
    """Enriches current input with conversation history"""

    def __init__(self):
        """Initialize context enricher"""
        pass

    def enrich_input(
        self,
        current_input: str,
        state: PersistentState
    ) -> EnrichedInput:
        """
        Combine current input with conversation context.

        Args:
            current_input: Current user input
            state: Conversation state with history

        Returns:
            Enriched input with context

        Example:
            Previous Q: "Where does it hurt?"
            Current: "My chest"
            Enriched: "pain in chest" (for pattern matching)
        """
        # If conversation just started and not awaiting response, no enrichment needed
        if not state.turns_history and not state.awaiting_response:
            return EnrichedInput(
                original_input=current_input,
                enriched_input=current_input,
                context_used={},
                enrichment_applied=False
            )

        context_used = {}
        enriched = current_input

        # Check if awaiting response to a question
        if state.awaiting_response and state.last_question:
            enriched = self._enrich_with_question_context(
                current_input,
                state.last_question,
                state
            )
            context_used["last_question"] = state.last_question
            logger.debug(
                f"Enriched with question context: '{current_input}' → '{enriched}'"
            )

        # Add extracted context from previous turns
        if state.extracted_context:
            enriched = self._enrich_with_extracted_context(
                enriched,
                state.extracted_context
            )
            context_used["extracted_context"] = state.extracted_context
            logger.debug(
                f"Enriched with extracted context: {state.extracted_context}"
            )

        # Add recent conversation context
        recent_turns = state.get_recent_turns(limit=3)
        if recent_turns:
            enriched = self._enrich_with_recent_turns(enriched, recent_turns)
            context_used["recent_turns"] = len(recent_turns)

        enrichment_applied = enriched != current_input

        return EnrichedInput(
            original_input=current_input,
            enriched_input=enriched,
            context_used=context_used,
            enrichment_applied=enrichment_applied
        )

    def _enrich_with_question_context(
        self,
        current_input: str,
        last_question: str,
        state: PersistentState
    ) -> str:
        """
        Enrich input based on the question that was asked.

        Handles common patterns like:
        - "Where does it hurt?" → "My chest" becomes "pain in chest"
        - "Which doctor?" → "Dr. Smith" becomes "appointment with Dr. Smith"
        """
        input_lower = current_input.lower().strip()
        question_lower = last_question.lower()

        # Pattern: "Where does it hurt?" or "Where is the pain?"
        if any(phrase in question_lower for phrase in ["where", "location", "which part"]):
            if "hurt" in question_lower or "pain" in question_lower:
                # Extract location from response - avoid duplicating "pain"
                if "pain" not in input_lower:
                    # Remove "my" prefix if present for cleaner enrichment
                    location = current_input
                    if input_lower.startswith("my "):
                        location = current_input[3:]  # Remove "my "
                    return f"pain in {location}"

        # Pattern: "Which doctor?" or "Who do you want to see?"
        if any(phrase in question_lower for phrase in ["which doctor", "who", "which provider"]):
            if "dr" not in input_lower and "doctor" not in input_lower:
                return f"see doctor {current_input}"

        # Pattern: "When?" or "What time?"
        if any(phrase in question_lower for phrase in ["when", "what time", "which day"]):
            if "appointment" in str(state.extracted_context.get("intent", "")):
                return f"appointment on {current_input}"

        # Pattern: Duration/timeframe questions
        if any(phrase in question_lower for phrase in ["how long", "when did", "how many"]):
            if any(word in input_lower for word in ["hour", "day", "week", "minute"]):
                if "started" not in input_lower:
                    # Don't add "ago" if already present
                    if input_lower.endswith(" ago"):
                        return f"started {current_input}"
                    else:
                        return f"started {current_input} ago"

        # Default: return as-is if no pattern matches
        return current_input

    def _enrich_with_extracted_context(
        self,
        current_input: str,
        extracted_context: Dict[str, Any]
    ) -> str:
        """
        Add relevant extracted context to input.

        Example:
            Context: {"symptom": "pain", "severity": "severe"}
            Input: "in my chest"
            Output: "severe pain in my chest"
        """
        input_lower = current_input.lower()

        # Don't duplicate if context already in input
        enrichment_parts = []

        # Add symptom if relevant
        if "symptom" in extracted_context:
            symptom = str(extracted_context["symptom"]).lower()
            if symptom not in input_lower:
                enrichment_parts.append(symptom)

        # Add severity if relevant
        if "severity" in extracted_context or "level" in extracted_context:
            severity = extracted_context.get("severity") or extracted_context.get("level")
            severity_str = str(severity).lower()
            if severity_str not in input_lower:
                enrichment_parts.append(severity_str)

        # Prepend enrichment
        if enrichment_parts:
            return f"{' '.join(enrichment_parts)} {current_input}"

        return current_input

    def _enrich_with_recent_turns(
        self,
        current_input: str,
        recent_turns: List[Turn]
    ) -> str:
        """
        Add context from recent conversation turns.

        Useful for pronoun resolution and topic continuation.
        """
        # For now, we rely mainly on extracted_context
        # Future: could implement pronoun resolution, coreference, etc.
        return current_input

    def extract_context_from_history(
        self,
        turns: List[Turn]
    ) -> Dict[str, Any]:
        """
        Extract accumulated context from conversation history.

        Args:
            turns: List of conversation turns

        Returns:
            Dictionary of extracted context
        """
        context = {}

        for turn in turns:
            # Merge extracted params from each turn
            if turn.extracted_params:
                context.update(turn.extracted_params)

            # Extract from matched moves
            if turn.matched_move:
                # Track conversation flow
                if "move_sequence" not in context:
                    context["move_sequence"] = []
                context["move_sequence"].append(turn.matched_move)

        return context

    def merge_contexts(
        self,
        base_context: Dict[str, Any],
        new_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge two context dictionaries, handling conflicts.

        Args:
            base_context: Existing context
            new_context: New context to merge

        Returns:
            Merged context
        """
        merged = base_context.copy()

        for key, value in new_context.items():
            if key in merged:
                # Handle list merging
                if isinstance(merged[key], list) and isinstance(value, list):
                    merged[key].extend(value)
                else:
                    # New value overwrites old
                    merged[key] = value
            else:
                merged[key] = value

        return merged

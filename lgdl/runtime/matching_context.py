"""
Matching Context for LGDL Pattern Matching

Provides rich contextual information to semantic matchers for grounded matching.
Includes game vocabulary, conversation history, filled slots, and successful patterns.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class MatchingContext:
    """Rich context for context-aware pattern matching.

    This context is provided to semantic matchers (especially LLM-based) to enable
    grounded understanding using:
    - Game-specific vocabulary (synonyms)
    - Conversation history (multi-turn context)
    - Filled slots (current state)
    - Successful patterns (learning from what works)

    Example:
        context = MatchingContext(
            game_name="medical_triage",
            game_description="Emergency room patient triage",
            vocabulary={"heart": ["ticker", "chest", "cardiovascular"]},
            conversation_history=[
                {"role": "assistant", "content": "What brings you in?"},
                {"role": "user", "content": "I'm not feeling well"}
            ],
            filled_slots={"pain_severity": 8},
            current_move="pain_assessment"
        )

    This context helps LLM understand that "my ticker hurts" means "chest pain"
    because "ticker" is a synonym for "heart/chest" in the game vocabulary.
    """

    game_name: str
    """Name of the game (domain)"""

    game_description: str = ""
    """Human-readable description of the game's purpose"""

    vocabulary: Dict[str, List[str]] = field(default_factory=dict)
    """Game-specific vocabulary mapping terms to synonyms.

    Format: {"canonical_term": ["synonym1", "synonym2", ...]}
    Example: {"heart": ["ticker", "chest", "cardiovascular"]}

    Used by LLM to understand domain-specific terminology and slang.
    """

    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    """Recent conversation turns for multi-turn context.

    Format: [{"role": "user"/"assistant", "content": "text"}, ...]
    Limited to last N turns (typically 5) to control prompt size.

    Helps LLM understand conversational flow and references.
    """

    filled_slots: Dict[str, Any] = field(default_factory=dict)
    """Currently filled slots in active move.

    Format: {"slot_name": value, ...}
    Example: {"pain_location": "chest", "pain_severity": 8}

    Helps LLM understand what information is already known.
    """

    current_move: Optional[str] = None
    """ID of the current move being evaluated, if any"""

    successful_patterns: List[str] = field(default_factory=list)
    """Recently successful pattern matches.

    These are patterns that led to successful task completion.
    Helps LLM learn from what has worked in the past.

    Limited to last N successful patterns (typically 10).
    """

    @classmethod
    def from_state(
        cls,
        compiled_game: Dict[str, Any],
        conversation_state: Optional[Any] = None
    ) -> "MatchingContext":
        """Build matching context from compiled game and conversation state.

        Args:
            compiled_game: Compiled game IR with vocabulary and metadata
            conversation_state: Optional conversation state with history and slots

        Returns:
            MatchingContext populated with available information
        """
        # Extract game metadata
        game_name = compiled_game.get("name", "unknown")
        game_description = compiled_game.get("description", "")
        vocabulary = compiled_game.get("vocabulary", {})

        # Extract conversation history (limit to last 5 turns)
        history = []
        if conversation_state and hasattr(conversation_state, "history"):
            # Conversation state has history as list of turn objects
            for turn in conversation_state.history[-5:]:
                if hasattr(turn, "user_input") and turn.user_input:
                    history.append({
                        "role": "user",
                        "content": turn.user_input
                    })
                if hasattr(turn, "response") and turn.response:
                    history.append({
                        "role": "assistant",
                        "content": turn.response
                    })

        # Extract filled slots
        slots = {}
        if conversation_state and hasattr(conversation_state, "awaiting_slot_for_move"):
            # Get slots for current move from state manager
            # Note: This requires state manager integration
            pass

        # Extract successful patterns (future: from learning engine)
        successful = []

        return cls(
            game_name=game_name,
            game_description=game_description,
            vocabulary=vocabulary,
            conversation_history=history,
            filled_slots=slots,
            current_move=None,
            successful_patterns=successful
        )

    @classmethod
    def empty(cls, game_name: str = "unknown") -> "MatchingContext":
        """Create empty context (for testing or stateless matching).

        Args:
            game_name: Name of the game

        Returns:
            MatchingContext with no history, slots, or vocabulary
        """
        return cls(
            game_name=game_name,
            game_description="",
            vocabulary={},
            conversation_history=[],
            filled_slots={},
            current_move=None,
            successful_patterns=[]
        )

    def has_vocabulary(self) -> bool:
        """Check if context has any vocabulary entries.

        Returns:
            True if vocabulary is non-empty
        """
        return len(self.vocabulary) > 0

    def has_history(self) -> bool:
        """Check if context has conversation history.

        Returns:
            True if history is non-empty
        """
        return len(self.conversation_history) > 0

    def get_relevant_vocabulary(self, text: str) -> Dict[str, List[str]]:
        """Get vocabulary entries relevant to given text.

        Filters vocabulary to only include terms/synonyms that appear in the text.
        This reduces prompt size for LLM calls.

        Args:
            text: User input text to check against

        Returns:
            Dictionary of relevant vocabulary entries
        """
        text_lower = text.lower()
        relevant = {}

        for term, synonyms in self.vocabulary.items():
            # Check if term or any synonym appears in text
            if term.lower() in text_lower:
                relevant[term] = synonyms
            else:
                for syn in synonyms:
                    if syn.lower() in text_lower:
                        relevant[term] = synonyms
                        break

        return relevant

    def get_recent_history(self, max_turns: int = 3) -> List[Dict[str, str]]:
        """Get most recent conversation turns.

        Args:
            max_turns: Maximum number of recent turns to return

        Returns:
            List of recent turns (most recent last)
        """
        return self.conversation_history[-max_turns:]

    def add_turn(self, role: str, content: str):
        """Add a turn to conversation history.

        Args:
            role: "user" or "assistant"
            content: Turn content
        """
        self.conversation_history.append({
            "role": role,
            "content": content
        })

        # Keep only last 10 turns to control memory
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

    def add_filled_slot(self, slot_name: str, value: Any):
        """Add a filled slot to context.

        Args:
            slot_name: Name of the slot
            value: Slot value
        """
        self.filled_slots[slot_name] = value

    def add_successful_pattern(self, pattern: str):
        """Record a successful pattern match.

        Args:
            pattern: Pattern text that matched successfully
        """
        self.successful_patterns.append(pattern)

        # Keep only last 10 successful patterns
        if len(self.successful_patterns) > 10:
            self.successful_patterns = self.successful_patterns[-10:]

    def to_summary(self) -> str:
        """Get human-readable summary of context.

        Returns:
            Formatted string describing context contents
        """
        lines = [
            f"Game: {self.game_name}",
            f"Description: {self.game_description or 'N/A'}",
            f"Vocabulary entries: {len(self.vocabulary)}",
            f"Conversation turns: {len(self.conversation_history)}",
            f"Filled slots: {len(self.filled_slots)}",
            f"Successful patterns: {len(self.successful_patterns)}",
        ]

        if self.current_move:
            lines.append(f"Current move: {self.current_move}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"MatchingContext(game={self.game_name}, "
            f"vocab={len(self.vocabulary)}, "
            f"history={len(self.conversation_history)}, "
            f"slots={len(self.filled_slots)})"
        )

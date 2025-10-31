"""Slot-filling manager for multi-turn conversations (v1.0)"""
import re
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from .state import StateManager


class SlotManager:
    """Manages slot-filling for multi-turn conversations"""

    def __init__(self, state_manager: Optional["StateManager"] = None):
        """
        Initialize SlotManager.

        Args:
            state_manager: Optional StateManager for persistent storage.
                           If None, uses in-memory storage (ephemeral).
        """
        self.state_manager = state_manager
        # In-memory storage (fallback or when no state_manager): {conversation_id: {move_id: {slot_name: value}}}
        self._slot_values: Dict[str, Dict[str, Dict[str, Any]]] = {}

    async def get_missing_slots(
        self,
        move: dict,
        conversation_id: str
    ) -> List[str]:
        """
        Return list of required slots not yet filled.

        Args:
            move: Compiled move IR with slots definition
            conversation_id: Conversation identifier

        Returns:
            List of slot names that are required but not filled
        """
        slots = move.get("slots", {})
        if not slots:
            return []

        move_id = move["id"]

        # Get filled slots (from persistent or in-memory storage)
        if self.state_manager:
            filled = await self.state_manager.persistent_storage.get_all_slots_for_move(conversation_id, move_id)
        else:
            filled = self._slot_values.get(conversation_id, {}).get(move_id, {})

        missing = []
        for slot_name, slot_def in slots.items():
            if slot_def.get("required", True):
                if slot_name not in filled:
                    # Check if there's a default value
                    if slot_def.get("default") is None:
                        missing.append(slot_name)

        return missing

    def validate_slot_value(
        self,
        slot_def: dict,
        value: Any
    ) -> Tuple[bool, Any]:
        """
        Validate and coerce value against slot type constraints.

        Args:
            slot_def: Slot definition from IR
            value: Raw value to validate

        Returns:
            Tuple of (is_valid, coerced_value)
        """
        slot_type = slot_def.get("type", "string")

        try:
            if slot_type == "string":
                return True, str(value)

            elif slot_type == "number":
                # Try to parse as number
                if isinstance(value, (int, float)):
                    return True, float(value)
                # Try to extract number from string
                num_match = re.search(r'-?\d+\.?\d*', str(value))
                if num_match:
                    return True, float(num_match.group())
                return False, None

            elif slot_type == "range":
                # Validate number is within range (inclusive bounds)
                # range(1, 10) accepts: 1.0, 1.5, 2.0, ..., 9.5, 10.0
                min_val = slot_def.get("min", 0)
                max_val = slot_def.get("max", 100)

                if isinstance(value, (int, float)):
                    num = float(value)
                else:
                    num_match = re.search(r'-?\d+\.?\d*', str(value))
                    if not num_match:
                        return False, None
                    num = float(num_match.group())

                # Inclusive bounds check
                if min_val <= num <= max_val:
                    return True, num
                return False, None

            elif slot_type == "enum":
                # Validate value is one of the enum options
                enum_values = slot_def.get("enum_values", [])
                value_str = str(value).lower()

                # Direct match
                for enum_val in enum_values:
                    if value_str == str(enum_val).lower():
                        return True, enum_val

                # Partial match
                for enum_val in enum_values:
                    if value_str in str(enum_val).lower() or str(enum_val).lower() in value_str:
                        return True, enum_val

                return False, None

            elif slot_type == "timeframe":
                # Parse timeframe expressions like "2 hours", "30 minutes", "1 week"
                value_str = str(value).lower()

                # Pattern: number + unit or "a/an" + unit
                patterns = [
                    r'(\d+)\s*(second|sec|s)s?',
                    r'(\d+)\s*(minute|min|m)s?',
                    r'(\d+)\s*(hour|hr|h)s?',
                    r'(\d+)\s*(day|d)s?',
                    r'(\d+)\s*(week|wk|w)s?',
                    r'(\d+)\s*(month|mo)s?',
                    r'(\d+)\s*(year|yr|y)s?',
                    r'an?\s+(second|minute|hour|day|week|month|year)',  # "a/an hour", "a day"
                ]

                for pattern in patterns:
                    match = re.search(pattern, value_str)
                    if match:
                        # Return original matched string
                        return True, value_str

                # Accept phrases like "just now", "recently", "a while ago", "ago"
                if any(phrase in value_str for phrase in ['just now', 'recently', 'a while', 'earlier', 'today', 'yesterday', 'ago']):
                    return True, value_str

                return False, None

            elif slot_type == "date":
                # Basic date parsing - accept various formats
                # This is simplified; production would use dateutil or similar
                value_str = str(value)
                date_patterns = [
                    r'\d{4}-\d{2}-\d{2}',  # ISO format
                    r'\d{1,2}/\d{1,2}/\d{2,4}',  # US format
                    r'\d{1,2}-\d{1,2}-\d{2,4}',  # Dashed format
                ]

                for pattern in date_patterns:
                    if re.search(pattern, value_str):
                        return True, value_str

                return False, None

            else:
                # Unknown type, accept as string
                return True, str(value)

        except (ValueError, TypeError):
            return False, None

    def extract_slot_from_input(
        self,
        input_text: str,
        slot_type: str,
        extracted_params: dict
    ) -> Optional[Any]:
        """
        Extract slot value from user input using pattern matching.

        Precedence order:
        1. Pattern-captured params (handled by caller)
        2. Type-specific extraction (this method)
        3. Whole input as fallback

        Args:
            input_text: Raw user input
            slot_type: Type of slot to extract
            extracted_params: Parameters extracted from pattern matching

        Returns:
            Extracted value or None if not found
        """
        if not input_text or not input_text.strip():
            return None

        input_text = input_text.strip()

        # Type-specific extraction
        if slot_type in ("number", "range"):
            # Extract first number from input
            num_match = re.search(r'-?\d+\.?\d*', input_text)
            if num_match:
                return float(num_match.group())
            # If no number found, fall through to return whole input

        elif slot_type == "enum":
            # For enum, return the whole input - validation will match against values
            return input_text

        # For string, timeframe, date: return whole input
        # More sophisticated extraction would use NER or LLM
        return input_text

    async def fill_slot(
        self,
        conversation_id: str,
        move_id: str,
        slot_name: str,
        value: Any,
        slot_type: str = "string"
    ) -> bool:
        """
        Store filled slot value in conversation state.

        Args:
            conversation_id: Conversation identifier
            move_id: Move identifier
            slot_name: Name of the slot
            value: Validated value to store
            slot_type: Type of slot (for metadata)

        Returns:
            True if value was stored successfully
        """
        # Use persistent storage if available
        if self.state_manager:
            await self.state_manager.persistent_storage.save_slot(
                conversation_id, move_id, slot_name, value, slot_type
            )
        else:
            # Fallback to in-memory storage
            if conversation_id not in self._slot_values:
                self._slot_values[conversation_id] = {}

            if move_id not in self._slot_values[conversation_id]:
                self._slot_values[conversation_id][move_id] = {}

            self._slot_values[conversation_id][move_id][slot_name] = value

        return True

    async def all_required_filled(
        self,
        move: dict,
        conversation_id: str
    ) -> bool:
        """
        Check if all required slots are filled.

        Args:
            move: Compiled move IR with slots definition
            conversation_id: Conversation identifier

        Returns:
            True if all required slots have values
        """
        missing = await self.get_missing_slots(move, conversation_id)
        return len(missing) == 0

    async def get_slot_values(
        self,
        move_id: str,
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        Get all filled slot values for a move.

        Args:
            move_id: Move identifier
            conversation_id: Conversation identifier

        Returns:
            Dictionary of slot name to value
        """
        if self.state_manager:
            return await self.state_manager.persistent_storage.get_all_slots_for_move(conversation_id, move_id)
        else:
            return self._slot_values.get(conversation_id, {}).get(move_id, {}).copy()

    async def clear_slots(
        self,
        conversation_id: str,
        move_id: str
    ):
        """
        Clear all slots for a move (when move completes).

        Args:
            conversation_id: Conversation identifier
            move_id: Move identifier
        """
        if self.state_manager:
            await self.state_manager.persistent_storage.clear_slots_for_move(conversation_id, move_id)
        else:
            if conversation_id in self._slot_values:
                if move_id in self._slot_values[conversation_id]:
                    del self._slot_values[conversation_id][move_id]

    async def get_slot_value(
        self,
        conversation_id: str,
        move_id: str,
        slot_name: str
    ) -> Optional[Any]:
        """
        Get a specific slot value.

        Args:
            conversation_id: Conversation identifier
            move_id: Move identifier
            slot_name: Name of the slot

        Returns:
            Slot value or None if not filled
        """
        if self.state_manager:
            return await self.state_manager.persistent_storage.get_slot(conversation_id, move_id, slot_name)
        else:
            return self._slot_values.get(conversation_id, {}).get(move_id, {}).get(slot_name)

    async def has_slot(
        self,
        conversation_id: str,
        move_id: str,
        slot_name: str
    ) -> bool:
        """
        Check if a slot has been filled.

        Args:
            conversation_id: Conversation identifier
            move_id: Move identifier
            slot_name: Name of the slot

        Returns:
            True if slot is filled
        """
        if self.state_manager:
            value = await self.state_manager.persistent_storage.get_slot(conversation_id, move_id, slot_name)
            return value is not None
        else:
            return slot_name in self._slot_values.get(conversation_id, {}).get(move_id, {})

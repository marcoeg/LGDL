"""
State management for multi-turn conversations.

Provides ephemeral (single-turn) and persistent (multi-turn) state tracking
to enable stateful conversations and context enrichment.

Copyright (c) 2025 Graziano Labs Corp.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Protocol
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """Single turn in a conversation"""
    turn_num: int
    timestamp: datetime
    user_input: str
    sanitized_input: str
    matched_move: Optional[str]
    confidence: float
    response: str
    extracted_params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PersistentState:
    """Conversation state that persists across turns"""
    conversation_id: str
    created_at: datetime
    updated_at: datetime
    turns_history: List[Turn] = field(default_factory=list)
    extracted_context: Dict[str, Any] = field(default_factory=dict)
    current_move_state: Optional[str] = None
    awaiting_response: bool = False
    last_question: Optional[str] = None
    # Slot-filling state (v1.0)
    awaiting_slot_for_move: Optional[str] = None
    awaiting_slot_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_turn(self, turn: Turn):
        """Add a turn to history"""
        self.turns_history.append(turn)
        self.updated_at = datetime.utcnow()

        # Update extracted context with any new parameters
        if turn.extracted_params:
            self.extracted_context.update(turn.extracted_params)

    def get_recent_turns(self, limit: int = 5) -> List[Turn]:
        """Get most recent N turns"""
        return self.turns_history[-limit:] if self.turns_history else []

    @property
    def turn_count(self) -> int:
        """Total number of turns in conversation"""
        return len(self.turns_history)


@dataclass
class EphemeralTurnState:
    """Transient state for a single turn"""
    user_input: str
    sanitized_input: str
    processing_start: datetime
    conversation_id: str
    turn_num: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class StorageBackend(Protocol):
    """Protocol for conversation state storage"""

    async def create_conversation(self, conversation_id: str) -> PersistentState:
        """Create a new conversation"""
        ...

    async def load_conversation(self, conversation_id: str) -> Optional[PersistentState]:
        """Load conversation state"""
        ...

    async def save_conversation(self, state: PersistentState) -> None:
        """Save conversation state"""
        ...

    async def delete_conversation(self, conversation_id: str) -> None:
        """Delete conversation"""
        ...

    async def cleanup_old_conversations(self, older_than: timedelta) -> int:
        """Remove old conversations, return count deleted"""
        ...


class TTLCache:
    """Simple TTL cache for ephemeral state"""

    def __init__(self, ttl: int = 300):
        """
        Initialize TTL cache.

        Args:
            ttl: Time to live in seconds (default 5 minutes)
        """
        self.ttl = ttl
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        async with self._lock:
            if key not in self._cache:
                return None

            value, expiry = self._cache[key]
            if datetime.utcnow() > expiry:
                del self._cache[key]
                return None

            return value

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache with TTL"""
        async with self._lock:
            expiry = datetime.utcnow() + timedelta(seconds=self.ttl)
            self._cache[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        """Remove value from cache"""
        async with self._lock:
            self._cache.pop(key, None)

    async def cleanup(self) -> int:
        """Remove expired entries, return count removed"""
        async with self._lock:
            now = datetime.utcnow()
            expired = [k for k, (_, exp) in self._cache.items() if now > exp]
            for key in expired:
                del self._cache[key]
            return len(expired)


class StateManager:
    """
    Manages conversation state across turns.

    Provides:
    - Ephemeral cache for fast single-turn data
    - Persistent storage for multi-turn conversation history
    - Thread-safe state access
    - Automatic cleanup of old conversations
    """

    def __init__(
        self,
        persistent_storage: StorageBackend,
        ephemeral_ttl: int = 300
    ):
        """
        Initialize state manager.

        Args:
            persistent_storage: Backend for persistent state
            ephemeral_ttl: TTL for ephemeral cache in seconds
        """
        self.persistent_storage = persistent_storage
        self.ephemeral_cache = TTLCache(ttl=ephemeral_ttl)
        self.state_lock = asyncio.Lock()

    async def get_or_create(self, conversation_id: str) -> PersistentState:
        """
        Get existing conversation or create new one.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Conversation state
        """
        # Check ephemeral cache first
        cached = await self.ephemeral_cache.get(f"persistent:{conversation_id}")
        if cached:
            logger.debug(f"Cache hit for conversation {conversation_id}")
            return cached

        # Load from persistent storage
        async with self.state_lock:
            state = await self.persistent_storage.load_conversation(conversation_id)

            if not state:
                logger.info(f"Creating new conversation {conversation_id}")
                state = await self.persistent_storage.create_conversation(conversation_id)

            # Cache for fast access
            await self.ephemeral_cache.set(f"persistent:{conversation_id}", state)
            return state

    async def update(
        self,
        conversation_id: str,
        turn: Turn,
        extracted_params: Optional[Dict[str, Any]] = None
    ) -> PersistentState:
        """
        Update conversation state with new turn.

        Args:
            conversation_id: Conversation identifier
            turn: Turn data to add
            extracted_params: Optional additional context

        Returns:
            Updated conversation state
        """
        async with self.state_lock:
            # Get current state
            state = await self.get_or_create(conversation_id)

            # Update turn with any additional params
            if extracted_params:
                turn.extracted_params.update(extracted_params)

            # Add turn to history
            state.add_turn(turn)

            # Save to persistent storage
            await self.persistent_storage.save_conversation(state)

            # Update cache
            await self.ephemeral_cache.set(f"persistent:{conversation_id}", state)

            logger.debug(
                f"Updated conversation {conversation_id}: "
                f"turn {turn.turn_num}, move {turn.matched_move}"
            )

            return state

    async def set_awaiting_response(
        self,
        conversation_id: str,
        question: str
    ) -> None:
        """
        Mark conversation as awaiting user response to a question.

        Args:
            conversation_id: Conversation identifier
            question: Question asked to user
        """
        async with self.state_lock:
            state = await self.get_or_create(conversation_id)
            state.awaiting_response = True
            state.last_question = question
            state.updated_at = datetime.utcnow()

            await self.persistent_storage.save_conversation(state)
            await self.ephemeral_cache.set(f"persistent:{conversation_id}", state)

    async def clear_awaiting_response(
        self,
        conversation_id: str
    ) -> Optional[str]:
        """
        Clear awaiting response flag and return the question.

        Args:
            conversation_id: Conversation identifier

        Returns:
            The question that was awaiting response, if any
        """
        async with self.state_lock:
            state = await self.get_or_create(conversation_id)

            question = state.last_question if state.awaiting_response else None

            state.awaiting_response = False
            state.last_question = None
            state.updated_at = datetime.utcnow()

            await self.persistent_storage.save_conversation(state)
            await self.ephemeral_cache.set(f"persistent:{conversation_id}", state)

            return question

    async def get_context(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get extracted context for conversation.

        Args:
            conversation_id: Conversation identifier

        Returns:
            Extracted context dictionary
        """
        state = await self.get_or_create(conversation_id)
        return state.extracted_context.copy()

    async def delete(self, conversation_id: str) -> None:
        """
        Delete conversation permanently.

        Args:
            conversation_id: Conversation identifier
        """
        async with self.state_lock:
            await self.persistent_storage.delete_conversation(conversation_id)
            await self.ephemeral_cache.delete(f"persistent:{conversation_id}")
            logger.info(f"Deleted conversation {conversation_id}")

    async def cleanup_old(self, older_than: timedelta) -> int:
        """
        Remove old conversations from storage.

        Args:
            older_than: Remove conversations older than this

        Returns:
            Number of conversations deleted
        """
        count = await self.persistent_storage.cleanup_old_conversations(older_than)
        logger.info(f"Cleaned up {count} old conversations")
        return count

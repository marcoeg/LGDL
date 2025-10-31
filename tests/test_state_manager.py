"""
Tests for state management.

Tests StateManager, PersistentState, and state persistence.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from lgdl.runtime.state import (
    StateManager,
    PersistentState,
    EphemeralTurnState,
    Turn,
    TTLCache
)
from lgdl.runtime.storage.sqlite import SQLiteStateStorage


@pytest.fixture
async def temp_db():
    """Create temporary database for testing"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def storage(temp_db):
    """Create SQLite storage backend"""
    return SQLiteStateStorage(temp_db)


@pytest.fixture
def state_manager(storage):
    """Create state manager with test storage"""
    return StateManager(persistent_storage=storage, ephemeral_ttl=2)


class TestTTLCache:
    """Test TTL cache functionality"""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test basic set and get"""
        cache = TTLCache(ttl=60)
        await cache.set("key1", "value1")

        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        """Test getting non-existent key"""
        cache = TTLCache(ttl=60)
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_expiry(self):
        """Test cache expiry"""
        cache = TTLCache(ttl=1)  # 1 second TTL
        await cache.set("key1", "value1")

        # Should exist immediately
        assert await cache.get("key1") == "value1"

        # Wait for expiry
        await asyncio.sleep(1.1)

        # Should be expired
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test cache deletion"""
        cache = TTLCache(ttl=60)
        await cache.set("key1", "value1")
        await cache.delete("key1")

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup of expired entries"""
        cache = TTLCache(ttl=1)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        await asyncio.sleep(1.1)

        # Cleanup should remove both expired entries
        count = await cache.cleanup()
        assert count == 2


class TestPersistentState:
    """Test PersistentState functionality"""

    def test_initialization(self):
        """Test state initialization"""
        state = PersistentState(
            conversation_id="test-123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        assert state.conversation_id == "test-123"
        assert state.turn_count == 0
        assert not state.awaiting_response
        assert state.extracted_context == {}

    def test_add_turn(self):
        """Test adding a turn to state"""
        state = PersistentState(
            conversation_id="test-123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        turn = Turn(
            turn_num=1,
            timestamp=datetime.utcnow(),
            user_input="Hello",
            sanitized_input="Hello",
            matched_move="greeting",
            confidence=0.95,
            response="Hi there!",
            extracted_params={"intent": "greeting"}
        )

        state.add_turn(turn)

        assert state.turn_count == 1
        assert state.extracted_context["intent"] == "greeting"
        assert state.turns_history[0] == turn

    def test_get_recent_turns(self):
        """Test getting recent turns"""
        state = PersistentState(
            conversation_id="test-123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Add 10 turns
        for i in range(10):
            turn = Turn(
                turn_num=i + 1,
                timestamp=datetime.utcnow(),
                user_input=f"Input {i}",
                sanitized_input=f"Input {i}",
                matched_move="test_move",
                confidence=0.9,
                response=f"Response {i}"
            )
            state.add_turn(turn)

        # Get last 5 turns
        recent = state.get_recent_turns(limit=5)
        assert len(recent) == 5
        assert recent[0].turn_num == 6
        assert recent[4].turn_num == 10


class TestSQLiteStorage:
    """Test SQLite storage backend"""

    @pytest.mark.asyncio
    async def test_create_conversation(self, storage):
        """Test creating a new conversation"""
        state = await storage.create_conversation("test-123")

        assert state.conversation_id == "test-123"
        assert state.turn_count == 0
        assert isinstance(state.created_at, datetime)

    @pytest.mark.asyncio
    async def test_load_nonexistent_conversation(self, storage):
        """Test loading non-existent conversation"""
        state = await storage.load_conversation("nonexistent")
        assert state is None

    @pytest.mark.asyncio
    async def test_save_and_load_conversation(self, storage):
        """Test saving and loading conversation"""
        # Create conversation
        state = await storage.create_conversation("test-456")

        # Add a turn
        turn = Turn(
            turn_num=1,
            timestamp=datetime.utcnow(),
            user_input="Test input",
            sanitized_input="Test input",
            matched_move="test_move",
            confidence=0.85,
            response="Test response",
            extracted_params={"key": "value"}
        )
        state.add_turn(turn)

        # Save
        await storage.save_conversation(state)

        # Load
        loaded = await storage.load_conversation("test-456")

        assert loaded is not None
        assert loaded.conversation_id == "test-456"
        assert loaded.turn_count == 1
        assert loaded.turns_history[0].user_input == "Test input"
        assert loaded.extracted_context["key"] == "value"

    @pytest.mark.asyncio
    async def test_delete_conversation(self, storage):
        """Test deleting a conversation"""
        state = await storage.create_conversation("test-789")
        await storage.delete_conversation("test-789")

        loaded = await storage.load_conversation("test-789")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_cleanup_old_conversations(self, storage):
        """Test cleaning up old conversations"""
        # Create conversation
        state = await storage.create_conversation("old-123")

        # Manually set old updated_at timestamp
        state.updated_at = datetime.utcnow() - timedelta(days=8)
        await storage.save_conversation(state)

        # Cleanup conversations older than 7 days
        count = await storage.cleanup_old_conversations(timedelta(days=7))

        assert count == 1

        # Verify deleted
        loaded = await storage.load_conversation("old-123")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_get_stats(self, storage):
        """Test getting storage statistics"""
        # Get initial count
        initial_stats = await storage.get_stats()
        initial_count = initial_stats["total_conversations"]

        # Create some conversations
        await storage.create_conversation("test-stats-1")
        await storage.create_conversation("test-stats-2")

        stats = await storage.get_stats()

        assert stats["total_conversations"] == initial_count + 2
        assert "db_path" in stats


class TestStateManager:
    """Test StateManager functionality"""

    @pytest.mark.asyncio
    async def test_get_or_create_new(self, state_manager):
        """Test getting or creating new conversation"""
        state = await state_manager.get_or_create("new-123")

        assert state.conversation_id == "new-123"
        assert state.turn_count == 0

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self, state_manager):
        """Test getting existing conversation"""
        # Create first
        state1 = await state_manager.get_or_create("existing-456")

        # Get again
        state2 = await state_manager.get_or_create("existing-456")

        assert state1.conversation_id == state2.conversation_id

    @pytest.mark.asyncio
    async def test_update_conversation(self, state_manager):
        """Test updating conversation with new turn"""
        state = await state_manager.get_or_create("update-789")

        turn = Turn(
            turn_num=1,
            timestamp=datetime.utcnow(),
            user_input="Update test",
            sanitized_input="Update test",
            matched_move="test_move",
            confidence=0.9,
            response="Response"
        )

        updated = await state_manager.update(
            "update-789",
            turn,
            extracted_params={"test": "value"}
        )

        assert updated.turn_count == 1
        assert updated.extracted_context["test"] == "value"

    @pytest.mark.asyncio
    async def test_set_awaiting_response(self, state_manager):
        """Test setting awaiting response flag"""
        await state_manager.get_or_create("awaiting-123")
        await state_manager.set_awaiting_response("awaiting-123", "What is your name?")

        state = await state_manager.get_or_create("awaiting-123")

        assert state.awaiting_response is True
        assert state.last_question == "What is your name?"

    @pytest.mark.asyncio
    async def test_clear_awaiting_response(self, state_manager):
        """Test clearing awaiting response flag"""
        await state_manager.get_or_create("clear-123")
        await state_manager.set_awaiting_response("clear-123", "Question?")

        question = await state_manager.clear_awaiting_response("clear-123")

        assert question == "Question?"

        state = await state_manager.get_or_create("clear-123")
        assert state.awaiting_response is False
        assert state.last_question is None

    @pytest.mark.asyncio
    async def test_get_context(self, state_manager):
        """Test getting extracted context"""
        state = await state_manager.get_or_create("context-123")

        turn = Turn(
            turn_num=1,
            timestamp=datetime.utcnow(),
            user_input="Test",
            sanitized_input="Test",
            matched_move="test_move",
            confidence=0.9,
            response="Response",
            extracted_params={"key1": "value1"}
        )

        await state_manager.update("context-123", turn)

        context = await state_manager.get_context("context-123")

        assert context["key1"] == "value1"

    @pytest.mark.asyncio
    async def test_delete_conversation(self, state_manager):
        """Test deleting conversation"""
        await state_manager.get_or_create("delete-123")
        await state_manager.delete("delete-123")

        # Should create new conversation on next get
        state = await state_manager.get_or_create("delete-123")
        assert state.turn_count == 0

    @pytest.mark.asyncio
    async def test_cache_hit(self, state_manager):
        """Test cache hit on repeated access"""
        # First access - creates and caches
        state1 = await state_manager.get_or_create("cache-123")

        # Second access - should hit cache
        state2 = await state_manager.get_or_create("cache-123")

        # Should be same instance (cached)
        assert state1 is state2

    @pytest.mark.asyncio
    async def test_concurrent_access(self, state_manager):
        """Test concurrent access to same conversation"""
        async def add_turn(turn_num):
            turn = Turn(
                turn_num=turn_num,
                timestamp=datetime.utcnow(),
                user_input=f"Input {turn_num}",
                sanitized_input=f"Input {turn_num}",
                matched_move="test_move",
                confidence=0.9,
                response=f"Response {turn_num}"
            )
            await state_manager.update("concurrent-123", turn)

        # Create conversation
        await state_manager.get_or_create("concurrent-123")

        # Add 5 turns concurrently
        await asyncio.gather(*[add_turn(i) for i in range(1, 6)])

        # Verify all turns were added
        state = await state_manager.get_or_create("concurrent-123")
        assert state.turn_count == 5

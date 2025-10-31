"""Unit tests for SlotManager (Phase 3)"""
import pytest
from lgdl.runtime.slots import SlotManager


@pytest.fixture
def slot_manager():
    """Create a SlotManager instance for testing (in-memory mode)"""
    return SlotManager(state_manager=None)


@pytest.fixture
def move_with_slots():
    """Sample move IR with slot definitions"""
    return {
        "id": "test_move",
        "slots": {
            "name": {
                "type": "string",
                "required": True,
                "default": None
            },
            "age": {
                "type": "number",
                "required": False,
                "default": None
            },
            "severity": {
                "type": "range",
                "required": True,
                "min": 1.0,
                "max": 10.0,
                "default": None
            }
        }
    }


def test_slot_validation_string(slot_manager):
    """Test string slot validation"""
    slot_def = {"type": "string"}

    valid, value = slot_manager.validate_slot_value(slot_def, "John Doe")
    assert valid is True
    assert value == "John Doe"

    valid, value = slot_manager.validate_slot_value(slot_def, 123)
    assert valid is True
    assert value == "123"


def test_slot_validation_number(slot_manager):
    """Test number slot validation"""
    slot_def = {"type": "number"}

    # Direct number
    valid, value = slot_manager.validate_slot_value(slot_def, 42)
    assert valid is True
    assert value == 42.0

    # String with number
    valid, value = slot_manager.validate_slot_value(slot_def, "the pain is 8 out of 10")
    assert valid is True
    assert value == 8.0

    # No number
    valid, value = slot_manager.validate_slot_value(slot_def, "no numbers here")
    assert valid is False


def test_slot_validation_range(slot_manager):
    """Test range slot validation with constraints"""
    slot_def = {"type": "range", "min": 1.0, "max": 10.0}

    # Valid range
    valid, value = slot_manager.validate_slot_value(slot_def, 5)
    assert valid is True
    assert value == 5.0

    # Extract from string
    valid, value = slot_manager.validate_slot_value(slot_def, "8 out of 10")
    assert valid is True
    assert value == 8.0

    # Below min
    valid, value = slot_manager.validate_slot_value(slot_def, 0)
    assert valid is False

    # Above max
    valid, value = slot_manager.validate_slot_value(slot_def, 11)
    assert valid is False

    # Edge cases
    valid, value = slot_manager.validate_slot_value(slot_def, 1)
    assert valid is True

    valid, value = slot_manager.validate_slot_value(slot_def, 10)
    assert valid is True


def test_slot_validation_enum(slot_manager):
    """Test enum slot validation"""
    slot_def = {"type": "enum", "enum_values": ["red", "green", "blue"]}

    # Exact match
    valid, value = slot_manager.validate_slot_value(slot_def, "red")
    assert valid is True
    assert value == "red"

    # Case insensitive
    valid, value = slot_manager.validate_slot_value(slot_def, "RED")
    assert valid is True
    assert value == "red"

    # Partial match
    valid, value = slot_manager.validate_slot_value(slot_def, "I like blue")
    assert valid is True
    assert value == "blue"

    # Invalid value
    valid, value = slot_manager.validate_slot_value(slot_def, "yellow")
    assert valid is False


def test_slot_validation_timeframe(slot_manager):
    """Test timeframe slot validation"""
    slot_def = {"type": "timeframe"}

    # Standard formats
    valid, value = slot_manager.validate_slot_value(slot_def, "2 hours")
    assert valid is True

    valid, value = slot_manager.validate_slot_value(slot_def, "30 minutes")
    assert valid is True

    valid, value = slot_manager.validate_slot_value(slot_def, "1 week")
    assert valid is True

    # Phrases
    valid, value = slot_manager.validate_slot_value(slot_def, "just now")
    assert valid is True

    valid, value = slot_manager.validate_slot_value(slot_def, "started yesterday")
    assert valid is True

    # Invalid
    valid, value = slot_manager.validate_slot_value(slot_def, "not a timeframe")
    assert valid is False


def test_slot_validation_timeframe_failures(slot_manager):
    """Test timeframe validation rejects nonsense input"""
    slot_def = {"type": "timeframe"}

    # Various invalid inputs
    valid, _ = slot_manager.validate_slot_value(slot_def, "asdfghjkl")
    assert valid is False

    valid, _ = slot_manager.validate_slot_value(slot_def, "123456789")
    assert valid is False

    valid, _ = slot_manager.validate_slot_value(slot_def, "!@#$%^&*()")
    assert valid is False


def test_slot_validation_date_failures(slot_manager):
    """Test date validation rejects nonsense input"""
    slot_def = {"type": "date"}

    # Invalid date formats
    valid, _ = slot_manager.validate_slot_value(slot_def, "not a date at all")
    assert valid is False

    valid, _ = slot_manager.validate_slot_value(slot_def, "asdfghjkl")
    assert valid is False

    valid, _ = slot_manager.validate_slot_value(slot_def, "yesterday")  # Phrase, not a date
    assert valid is False


def test_slot_validation_number_no_extraction(slot_manager):
    """Test that number validation fails when no number present"""
    slot_def = {"type": "number"}

    # No number in input
    valid, _ = slot_manager.validate_slot_value(slot_def, "no numbers here")
    assert valid is False

    valid, _ = slot_manager.validate_slot_value(slot_def, "asdfghjkl")
    assert valid is False


@pytest.mark.asyncio
async def test_missing_slot_detection(slot_manager, move_with_slots):
    """Test detection of missing required slots"""
    conv_id = "test_conv"

    # All slots missing initially
    missing = await slot_manager.get_missing_slots(move_with_slots, conv_id)
    assert "name" in missing
    assert "severity" in missing
    assert "age" not in missing  # Optional slot

    # Fill one slot
    await slot_manager.fill_slot(conv_id, "test_move", "name", "Alice")
    missing = await slot_manager.get_missing_slots(move_with_slots, conv_id)
    assert "name" not in missing
    assert "severity" in missing


@pytest.mark.asyncio
async def test_all_slots_filled_check(slot_manager, move_with_slots):
    """Test checking if all required slots are filled"""
    conv_id = "test_conv"

    # Not all filled initially
    assert await slot_manager.all_required_filled(move_with_slots, conv_id) is False

    # Fill required slots
    await slot_manager.fill_slot(conv_id, "test_move", "name", "Bob")
    assert await slot_manager.all_required_filled(move_with_slots, conv_id) is False

    await slot_manager.fill_slot(conv_id, "test_move", "severity", 7.0)
    assert await slot_manager.all_required_filled(move_with_slots, conv_id) is True


@pytest.mark.asyncio
async def test_slot_storage_and_retrieval(slot_manager):
    """Test storing and retrieving slot values"""
    conv_id = "test_conv"
    move_id = "test_move"

    # Store values
    await slot_manager.fill_slot(conv_id, move_id, "name", "Charlie")
    await slot_manager.fill_slot(conv_id, move_id, "age", 30)

    # Retrieve specific value
    assert await slot_manager.get_slot_value(conv_id, move_id, "name") == "Charlie"
    assert await slot_manager.get_slot_value(conv_id, move_id, "age") == 30
    assert await slot_manager.get_slot_value(conv_id, move_id, "nonexistent") is None

    # Retrieve all values
    all_values = await slot_manager.get_slot_values(move_id, conv_id)
    assert all_values == {"name": "Charlie", "age": 30}


@pytest.mark.asyncio
async def test_slot_clearing(slot_manager):
    """Test clearing slots after move completion"""
    conv_id = "test_conv"
    move_id = "test_move"

    # Fill some slots
    await slot_manager.fill_slot(conv_id, move_id, "name", "David")
    await slot_manager.fill_slot(conv_id, move_id, "age", 25)

    assert await slot_manager.has_slot(conv_id, move_id, "name") is True

    # Clear slots
    await slot_manager.clear_slots(conv_id, move_id)

    assert await slot_manager.has_slot(conv_id, move_id, "name") is False
    assert await slot_manager.get_slot_values(move_id, conv_id) == {}


@pytest.mark.asyncio
async def test_has_slot(slot_manager):
    """Test checking if a slot exists"""
    conv_id = "test_conv"
    move_id = "test_move"

    assert await slot_manager.has_slot(conv_id, move_id, "name") is False

    await slot_manager.fill_slot(conv_id, move_id, "name", "Eve")
    assert await slot_manager.has_slot(conv_id, move_id, "name") is True
    assert await slot_manager.has_slot(conv_id, move_id, "age") is False


def test_extract_slot_from_input(slot_manager):
    """Test extracting slot value from user input"""
    # String extraction (returns trimmed input)
    value = slot_manager.extract_slot_from_input("My chest", "string", {})
    assert value == "My chest"

    # Number extraction (extracts first number)
    value = slot_manager.extract_slot_from_input("  8 out of 10  ", "number", {})
    assert value == 8.0  # Now extracts the number

    value = slot_manager.extract_slot_from_input("the pain is 7", "number", {})
    assert value == 7.0

    value = slot_manager.extract_slot_from_input("around 9.5", "range", {})
    assert value == 9.5

    # Empty input
    value = slot_manager.extract_slot_from_input("", "string", {})
    assert value is None

    # Enum extraction (returns whole input for validation)
    value = slot_manager.extract_slot_from_input("I like blue", "enum", {})
    assert value == "I like blue"


@pytest.mark.asyncio
async def test_multiple_conversations(slot_manager):
    """Test that slots are isolated per conversation"""
    conv1 = "conv1"
    conv2 = "conv2"
    move_id = "test_move"

    # Fill slots for conv1
    await slot_manager.fill_slot(conv1, move_id, "name", "User1")

    # Fill slots for conv2
    await slot_manager.fill_slot(conv2, move_id, "name", "User2")

    # Verify isolation
    assert await slot_manager.get_slot_value(conv1, move_id, "name") == "User1"
    assert await slot_manager.get_slot_value(conv2, move_id, "name") == "User2"


@pytest.mark.asyncio
async def test_multiple_moves_per_conversation(slot_manager):
    """Test that slots are isolated per move within a conversation"""
    conv_id = "test_conv"
    move1 = "move1"
    move2 = "move2"

    # Fill slots for different moves
    await slot_manager.fill_slot(conv_id, move1, "name", "Alice")
    await slot_manager.fill_slot(conv_id, move2, "name", "Bob")

    # Verify isolation
    assert await slot_manager.get_slot_value(conv_id, move1, "name") == "Alice"
    assert await slot_manager.get_slot_value(conv_id, move2, "name") == "Bob"


@pytest.mark.asyncio
async def test_slot_with_default_value(slot_manager):
    """Test slots with default values"""
    move = {
        "id": "test_move",
        "slots": {
            "count": {
                "type": "number",
                "required": False,
                "default": 1
            }
        }
    }

    conv_id = "test_conv"

    # Slot with default is not missing
    missing = await slot_manager.get_missing_slots(move, conv_id)
    assert "count" not in missing


@pytest.mark.asyncio
async def test_empty_move_no_slots(slot_manager):
    """Test move without slots"""
    move_no_slots = {"id": "test_move"}
    conv_id = "test_conv"

    missing = await slot_manager.get_missing_slots(move_no_slots, conv_id)
    assert missing == []

    assert await slot_manager.all_required_filled(move_no_slots, conv_id) is True


@pytest.mark.asyncio
async def test_slot_persistence_with_state_manager():
    """Test that slots persist through StateManager storage"""
    import tempfile
    import os
    from lgdl.runtime.state import StateManager
    from lgdl.runtime.storage.sqlite import SQLiteStateStorage
    from lgdl.runtime.slots import SlotManager

    # Create temp database
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_slots.db")
    storage = SQLiteStateStorage(db_path)

    state_manager = StateManager(persistent_storage=storage, ephemeral_ttl=300)
    slot_manager = SlotManager(state_manager)

    conv_id = "persist_test"
    move_id = "test_move"

    # Fill slots
    await slot_manager.fill_slot(conv_id, move_id, "name", "Alice", "string")
    await slot_manager.fill_slot(conv_id, move_id, "age", 30, "number")

    # Retrieve from persistent storage
    assert await slot_manager.get_slot_value(conv_id, move_id, "name") == "Alice"
    assert await slot_manager.get_slot_value(conv_id, move_id, "age") == 30

    # Get all slots
    all_slots = await slot_manager.get_slot_values(move_id, conv_id)
    assert all_slots == {"name": "Alice", "age": 30}

    # Clear slots
    await slot_manager.clear_slots(conv_id, move_id)
    assert await slot_manager.get_slot_value(conv_id, move_id, "name") is None


@pytest.mark.asyncio
async def test_slot_persistence_survives_restart():
    """Test that slots persist across StateManager instances (simulated restart)"""
    import tempfile
    import os
    from lgdl.runtime.state import StateManager
    from lgdl.runtime.storage.sqlite import SQLiteStateStorage
    from lgdl.runtime.slots import SlotManager

    # Create temp database
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_slots_restart.db")

    # First session
    storage1 = SQLiteStateStorage(db_path)
    state_manager1 = StateManager(persistent_storage=storage1, ephemeral_ttl=300)
    slot_manager1 = SlotManager(state_manager1)

    conv_id = "restart_test"
    move_id = "test_move"

    await slot_manager1.fill_slot(conv_id, move_id, "location", "chest", "string")
    await slot_manager1.fill_slot(conv_id, move_id, "severity", 8.0, "range")

    # Second session (simulated restart)
    storage2 = SQLiteStateStorage(db_path)
    state_manager2 = StateManager(persistent_storage=storage2, ephemeral_ttl=300)
    slot_manager2 = SlotManager(state_manager2)

    # Verify slots survived restart
    assert await slot_manager2.get_slot_value(conv_id, move_id, "location") == "chest"
    assert await slot_manager2.get_slot_value(conv_id, move_id, "severity") == 8.0

    all_slots = await slot_manager2.get_slot_values(move_id, conv_id)
    assert all_slots == {"location": "chest", "severity": 8.0}


def test_slot_extraction_precedence():
    """Test that numeric extraction works correctly for different input formats"""
    slot_manager = SlotManager(state_manager=None)

    # Test number extraction from various formats
    assert slot_manager.extract_slot_from_input("8", "number", {}) == 8.0
    assert slot_manager.extract_slot_from_input("8.5", "number", {}) == 8.5
    assert slot_manager.extract_slot_from_input("the pain is 7", "number", {}) == 7.0
    assert slot_manager.extract_slot_from_input("about 9 out of 10", "number", {}) == 9.0

    # Test that pattern params are preferred (handled by engine, but document here)
    # When engine sees params["severity"] = 8, it uses that before calling extract_slot_from_input
    # This test just verifies extraction works independently

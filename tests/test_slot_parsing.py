"""Tests for slot-filling grammar parsing (Phase 1)"""
import pytest
from lgdl.parser.parser import parse_lgdl
from lgdl.parser.ast import SlotBlock, SlotDefinition


def test_parse_simple_slots():
    """Test parsing a move with simple slot definitions"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")
    assert game is not None
    assert game.name == "test_slots"

    # Find the simple_slot_test move
    simple_move = next((m for m in game.moves if m.name == "simple_slot_test"), None)
    assert simple_move is not None

    # Check slots block exists
    assert simple_move.slots is not None
    assert isinstance(simple_move.slots, SlotBlock)
    assert len(simple_move.slots.slots) == 2

    # Check name slot
    name_slot = next((s for s in simple_move.slots.slots if s.name == "name"), None)
    assert name_slot is not None
    assert name_slot.slot_type == "string"
    assert name_slot.required == True
    assert name_slot.optional == False

    # Check age slot
    age_slot = next((s for s in simple_move.slots.slots if s.name == "age"), None)
    assert age_slot is not None
    assert age_slot.slot_type == "number"
    assert age_slot.required == False
    assert age_slot.optional == True


def test_parse_range_slot():
    """Test parsing range slot type"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")

    range_move = next((m for m in game.moves if m.name == "range_slot_test"), None)
    assert range_move is not None
    assert range_move.slots is not None

    severity_slot = range_move.slots.slots[0]
    assert severity_slot.name == "severity"
    assert severity_slot.slot_type == "range"
    assert severity_slot.min_value == 1.0
    assert severity_slot.max_value == 10.0
    assert severity_slot.required == True


def test_parse_enum_slot():
    """Test parsing enum slot type"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")

    enum_move = next((m for m in game.moves if m.name == "enum_slot_test"), None)
    assert enum_move is not None
    assert enum_move.slots is not None

    color_slot = enum_move.slots.slots[0]
    assert color_slot.name == "color"
    assert color_slot.slot_type == "enum"
    assert color_slot.enum_values == ["red", "green", "blue"]
    assert color_slot.required == True


def test_parse_default_slot():
    """Test parsing slot with default value"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")

    optional_move = next((m for m in game.moves if m.name == "optional_slot_test"), None)
    assert optional_move is not None
    assert optional_move.slots is not None
    assert len(optional_move.slots.slots) == 3

    # Check default slot
    count_slot = next((s for s in optional_move.slots.slots if s.name == "count"), None)
    assert count_slot is not None
    assert count_slot.slot_type == "number"
    assert count_slot.default == 1.0


def test_parse_slot_conditions():
    """Test parsing slot conditions in when blocks"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")

    simple_move = next((m for m in game.moves if m.name == "simple_slot_test"), None)
    assert simple_move is not None

    # Check for slot_missing condition block
    slot_missing_blocks = [b for b in simple_move.blocks
                           if b.kind == "when"
                           and b.condition.get("special") == "slot_missing"]
    assert len(slot_missing_blocks) >= 1

    # Check for all_slots_filled condition block
    all_filled_blocks = [b for b in simple_move.blocks
                        if b.kind == "when"
                        and b.condition.get("special") == "all_slots_filled"]
    assert len(all_filled_blocks) >= 1


def test_parse_prompt_slot_action():
    """Test parsing prompt: action for slots"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")

    simple_move = next((m for m in game.moves if m.name == "simple_slot_test"), None)
    assert simple_move is not None

    # Find the when slot is missing block
    slot_missing_blocks = [b for b in simple_move.blocks
                           if b.kind == "when"
                           and b.condition.get("special") == "slot_missing"]

    assert len(slot_missing_blocks) > 0
    block = slot_missing_blocks[0]
    assert len(block.actions) > 0

    # Check the prompt action
    prompt_action = block.actions[0]
    assert prompt_action.type == "respond"
    assert prompt_action.data.get("kind") == "prompt_slot"
    assert "What is your name?" in prompt_action.data.get("text", "")


def test_backward_compatibility():
    """Test that moves without slots still parse correctly"""
    game = parse_lgdl("examples/medical/game.lgdl")
    assert game is not None
    assert game.name == "medical_scheduling"

    # All existing moves should have slots=None
    for move in game.moves:
        # Slots should be None for moves without slot definitions
        if move.slots is not None:
            # If slots exist, they should be a SlotBlock with empty list
            assert isinstance(move.slots, SlotBlock)


def test_multiple_slot_modifiers():
    """Test that slot modifiers are parsed correctly"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")

    optional_move = next((m for m in game.moves if m.name == "optional_slot_test"), None)
    assert optional_move is not None

    # Check required slot
    location = next((s for s in optional_move.slots.slots if s.name == "location"), None)
    assert location.required == True
    assert location.optional == False

    # Check optional slot
    details = next((s for s in optional_move.slots.slots if s.name == "details"), None)
    assert details.required == False
    assert details.optional == True

    # Check default slot
    count = next((s for s in optional_move.slots.slots if s.name == "count"), None)
    assert count.default is not None


def test_slot_condition_with_slot_name():
    """Test that slot conditions capture the slot name"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")

    simple_move = next((m for m in game.moves if m.name == "simple_slot_test"), None)
    slot_missing_block = next((b for b in simple_move.blocks
                               if b.kind == "when"
                               and b.condition.get("special") == "slot_missing"), None)

    assert slot_missing_block is not None
    assert slot_missing_block.condition.get("slot") == "name"

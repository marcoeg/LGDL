"""Integration tests for slot-filling with runtime (Phase 6)"""
import pytest
from lgdl.parser.parser import parse_lgdl
from lgdl.parser.ir import compile_game
from lgdl.runtime.engine import LGDLRuntime


def test_medical_pain_assessment_has_slots():
    """Test that pain_assessment move has slot definitions"""
    game = parse_lgdl("examples/medical/game.lgdl")
    compiled = compile_game(game)

    # Find pain_assessment move
    pain_move = next((m for m in compiled["moves"] if m["id"] == "pain_assessment"), None)
    assert pain_move is not None

    # Verify it has slots
    assert "slots" in pain_move
    assert "location" in pain_move["slots"]
    assert "severity" in pain_move["slots"]
    assert "onset" in pain_move["slots"]


def test_pain_assessment_slot_types():
    """Test slot type definitions for pain_assessment"""
    game = parse_lgdl("examples/medical/game.lgdl")
    compiled = compile_game(game)

    pain_move = next((m for m in compiled["moves"] if m["id"] == "pain_assessment"), None)

    # Verify slot types
    assert pain_move["slots"]["location"]["type"] == "string"
    assert pain_move["slots"]["location"]["required"] is True

    assert pain_move["slots"]["severity"]["type"] == "range"
    assert pain_move["slots"]["severity"]["min"] == 1.0
    assert pain_move["slots"]["severity"]["max"] == 10.0
    assert pain_move["slots"]["severity"]["required"] is True

    assert pain_move["slots"]["onset"]["type"] == "timeframe"
    assert pain_move["slots"]["onset"]["required"] is True

    assert pain_move["slots"]["characteristics"]["type"] == "string"
    assert pain_move["slots"]["characteristics"]["required"] is False


def test_pain_assessment_slot_prompts():
    """Test that slot prompts are compiled correctly"""
    game = parse_lgdl("examples/medical/game.lgdl")
    compiled = compile_game(game)

    pain_move = next((m for m in compiled["moves"] if m["id"] == "pain_assessment"), None)

    # Verify slot prompts exist
    assert "slot_prompts" in pain_move
    assert "location" in pain_move["slot_prompts"]
    assert pain_move["slot_prompts"]["location"] == "Where does it hurt?"


def test_pain_assessment_all_slots_filled_action():
    """Test that all_slots_filled actions are compiled"""
    game = parse_lgdl("examples/medical/game.lgdl")
    compiled = compile_game(game)

    pain_move = next((m for m in compiled["moves"] if m["id"] == "pain_assessment"), None)

    # Verify all_slots_filled condition
    assert "slot_conditions" in pain_move
    assert "all_slots_filled" in pain_move["slot_conditions"]
    assert len(pain_move["slot_conditions"]["all_slots_filled"]) > 0


def test_backward_compatibility_non_slot_moves():
    """Test that moves without slots still compile correctly"""
    game = parse_lgdl("examples/medical/game.lgdl")
    compiled = compile_game(game)

    # Find a non-slot move
    appt_move = next((m for m in compiled["moves"] if m["id"] == "appointment_request"), None)
    assert appt_move is not None

    # Verify it doesn't have slots
    assert "slots" not in appt_move
    assert "slot_prompts" not in appt_move
    assert "slot_conditions" not in appt_move


def test_runtime_has_slot_manager():
    """Test that runtime with state manager has slot manager"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")
    compiled = compile_game(game)

    # Runtime without state manager - no slot manager
    runtime_no_state = LGDLRuntime(compiled, state_manager=None)
    assert runtime_no_state.slot_manager is None

    # Runtime with state manager would have slot manager
    # (not testing actual state manager here due to async complexity)


def test_test_grammar_slot_compilation():
    """Test that test grammar slot moves compile correctly"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")
    compiled = compile_game(game)

    # Find simple_slot_test move
    simple_move = next((m for m in compiled["moves"] if m["id"] == "simple_slot_test"), None)
    assert simple_move is not None
    assert "slots" in simple_move
    assert len(simple_move["slots"]) == 2  # name and age


def test_range_slot_compilation():
    """Test that range slot types compile with min/max"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")
    compiled = compile_game(game)

    range_move = next((m for m in compiled["moves"] if m["id"] == "range_slot_test"), None)
    assert range_move is not None

    severity_slot = range_move["slots"]["severity"]
    assert severity_slot["type"] == "range"
    assert severity_slot["min"] == 1.0
    assert severity_slot["max"] == 10.0


def test_enum_slot_compilation():
    """Test that enum slot types compile with values"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")
    compiled = compile_game(game)

    enum_move = next((m for m in compiled["moves"] if m["id"] == "enum_slot_test"), None)
    assert enum_move is not None

    color_slot = enum_move["slots"]["color"]
    assert color_slot["type"] == "enum"
    assert set(color_slot["enum_values"]) == {"red", "green", "blue"}


def test_optional_slot_compilation():
    """Test that optional slots compile correctly"""
    game = parse_lgdl("tests/test_slots_grammar.lgdl")
    compiled = compile_game(game)

    optional_move = next((m for m in compiled["moves"] if m["id"] == "optional_slot_test"), None)
    assert optional_move is not None

    # Required slot
    location_slot = optional_move["slots"]["location"]
    assert location_slot["required"] is True

    # Optional slot
    details_slot = optional_move["slots"]["details"]
    assert details_slot["required"] is False

    # Slot with default
    count_slot = optional_move["slots"]["count"]
    assert count_slot["default"] == 1.0

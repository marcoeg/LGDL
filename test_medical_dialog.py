"""Test medical slot-filling dialog end-to-end"""
import asyncio
from lgdl.parser.parser import parse_lgdl
from lgdl.parser.ir import compile_game
from lgdl.runtime.engine import LGDLRuntime
from lgdl.runtime.state import StateManager
from lgdl.runtime.storage.sqlite import SQLiteStateStorage
import tempfile
import os


async def test_pain_dialog():
    """Test a realistic pain assessment dialog"""
    # Setup
    game = parse_lgdl("examples/medical/game.lgdl")
    compiled = compile_game(game)

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_medical.db")
    storage = SQLiteStateStorage(db_path)
    state_manager = StateManager(persistent_storage=storage, ephemeral_ttl=300)

    # Add capability contract so we can test the full flow
    capability_contract = "examples/medical/capability_contract.json"
    runtime = LGDLRuntime(
        compiled,
        capability_contract_path=capability_contract,
        state_manager=state_manager
    )

    conv_id = "medical_test_001"
    user_id = "patient_001"

    print("=" * 60)
    print("MEDICAL SLOT-FILLING DIALOG TEST")
    print("=" * 60)

    # Turn 1: Patient initiates with vague complaint
    print("\n[TURN 1]")
    print("Patient: I'm in pain")
    result1 = await runtime.process_turn(conv_id, user_id, "I'm in pain", {})
    print(f"Move: {result1['move_id']}")
    print(f"Confidence: {result1['confidence']:.2f}")
    print(f"System: {result1['response']}")
    if 'awaiting_slot' in result1:
        print(f"Awaiting slot: {result1['awaiting_slot']}")

    # Turn 2: Patient answers location question
    print("\n[TURN 2]")
    print("Patient: My chest")
    result2 = await runtime.process_turn(conv_id, user_id, "My chest", {})
    print(f"Move: {result2['move_id']}")
    print(f"System: {result2['response']}")
    if 'awaiting_slot' in result2:
        print(f"Awaiting slot: {result2['awaiting_slot']}")

    # Turn 3: Patient provides severity
    print("\n[TURN 3]")
    print("Patient: 8 out of 10")
    result3 = await runtime.process_turn(conv_id, user_id, "8 out of 10", {})
    print(f"Move: {result3['move_id']}")
    print(f"System: {result3['response']}")
    if 'awaiting_slot' in result3:
        print(f"Awaiting slot: {result3['awaiting_slot']}")

    # Turn 4: Patient provides onset
    print("\n[TURN 4]")
    print("Patient: About an hour ago")
    result4 = await runtime.process_turn(conv_id, user_id, "About an hour ago", {})
    print(f"Move: {result4['move_id']}")
    print(f"System: {result4['response']}")
    if 'slots_filled' in result4:
        print(f"Slots filled: {result4['slots_filled']}")

    print("\n" + "=" * 60)
    print("DIALOG COMPLETE")
    print("=" * 60)

    # Verify the flow worked
    assert result1['move_id'] == 'pain_assessment'
    assert 'awaiting_slot' in result1

    assert result2['move_id'] == 'pain_assessment'
    assert 'awaiting_slot' in result2

    assert result3['move_id'] == 'pain_assessment'
    assert 'awaiting_slot' in result3

    assert result4['move_id'] == 'pain_assessment'
    if 'slots_filled' in result4:
        print("\n✅ All slots successfully filled!")
        print(f"   Location: {result4['slots_filled'].get('location')}")
        print(f"   Severity: {result4['slots_filled'].get('severity')}")
        print(f"   Onset: {result4['slots_filled'].get('onset')}")
        assert result4['slots_filled']['location'] == 'My chest'
        assert result4['slots_filled']['severity'] == 8.0
        assert 'ago' in result4['slots_filled']['onset'].lower()
    else:
        raise AssertionError("slots_filled should be in result")

    print("\n✅ Slot-filling dialog test PASSED!")


async def test_pattern_extraction_dialog():
    """Test dialog where slots are extracted from patterns"""
    game = parse_lgdl("examples/medical/game.lgdl")
    compiled = compile_game(game)

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_pattern.db")
    storage = SQLiteStateStorage(db_path)
    state_manager = StateManager(persistent_storage=storage, ephemeral_ttl=300)
    runtime = LGDLRuntime(compiled, state_manager=state_manager)

    conv_id = "pattern_test_001"
    user_id = "patient_002"

    print("\n" + "=" * 60)
    print("PATTERN EXTRACTION DIALOG TEST")
    print("=" * 60)

    # Turn 1: Patient provides location in initial utterance
    print("\n[TURN 1]")
    print("Patient: I have pain in my chest")
    result1 = await runtime.process_turn(conv_id, user_id, "I have pain in my chest", {})
    print(f"Move: {result1['move_id']}")
    print(f"System: {result1['response']}")
    if 'awaiting_slot' in result1:
        print(f"Awaiting slot: {result1['awaiting_slot']}")
        print("✅ Location extracted from pattern, now asking for severity")

    # Turn 2: Provide severity
    print("\n[TURN 2]")
    print("Patient: 9")
    result2 = await runtime.process_turn(conv_id, user_id, "9", {})
    print(f"System: {result2['response']}")
    if 'awaiting_slot' in result2:
        print(f"Awaiting slot: {result2['awaiting_slot']}")

    # Turn 3: Provide onset
    print("\n[TURN 3]")
    print("Patient: Started 30 minutes ago")
    result3 = await runtime.process_turn(conv_id, user_id, "Started 30 minutes ago", {})
    print(f"System: {result3['response']}")
    if 'slots_filled' in result3:
        print(f"✅ All slots filled: {result3['slots_filled']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_pain_dialog())
    asyncio.run(test_pattern_extraction_dialog())

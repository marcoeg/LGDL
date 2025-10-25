"""
Tests for negotiation state management and clarification loops.

Copyright (c) 2025 Graziano Labs Corp.
"""

import pytest
from lgdl.runtime.negotiation import NegotiationState, NegotiationManager


# NegotiationState Unit Tests

def test_negotiation_state_initialization():
    """NegotiationState initializes with correct defaults."""
    state = NegotiationState()
    assert state.round == 0
    assert state.history == []
    assert state.deltas == []
    assert state.terminated is False
    assert state.reason is None


def test_add_turn():
    """Adding turns updates history and calculates deltas."""
    state = NegotiationState()

    # First turn (no delta)
    state.add_turn("user", "I need an appointment", 0.65)
    assert len(state.history) == 1
    assert state.history[0]["role"] == "user"
    assert state.history[0]["content"] == "I need an appointment"
    assert state.history[0]["confidence"] == 0.65
    assert len(state.deltas) == 0  # No delta for first turn

    # Second turn (delta calculated from previous turn)
    state.add_turn("assistant", "With which doctor?", 0.65)
    assert len(state.history) == 2
    assert len(state.deltas) == 1  # Delta from previous turn
    assert state.deltas[0] == pytest.approx(0.0, abs=0.01)  # 0.65 - 0.65

    # Third turn (delta from second turn)
    state.add_turn("user", "Dr. Smith", 0.85)
    assert len(state.history) == 3
    assert len(state.deltas) == 2
    assert state.deltas[1] == pytest.approx(0.20, abs=0.01)  # 0.85 - 0.65


def test_should_stop_threshold_met():
    """Stop condition 1: Confidence crosses threshold."""
    state = NegotiationState()
    state.round = 1

    should_stop, reason = state.should_stop(confidence=0.90, threshold=0.85)
    assert should_stop is True
    assert reason == "threshold_met"


def test_should_stop_max_rounds():
    """Stop condition 2: Maximum rounds reached."""
    state = NegotiationState()
    state.round = 3

    should_stop, reason = state.should_stop(
        confidence=0.70,
        threshold=0.85,
        max_rounds=3
    )
    assert should_stop is True
    assert reason == "max_rounds"


def test_should_stop_stagnation():
    """Stop condition 3: No progress for 2 consecutive rounds."""
    state = NegotiationState()
    state.round = 2
    state.deltas = [0.02, 0.01]  # Both below epsilon (0.05)

    should_stop, reason = state.should_stop(
        confidence=0.70,
        threshold=0.85,
        stagnation_epsilon=0.05
    )
    assert should_stop is True
    assert reason == "stagnation"


def test_should_continue():
    """Negotiation continues when no stop conditions met."""
    state = NegotiationState()
    state.round = 1
    state.deltas = [0.10]  # Good progress

    should_stop, reason = state.should_stop(
        confidence=0.75,
        threshold=0.85,
        max_rounds=3,
        stagnation_epsilon=0.05
    )
    assert should_stop is False
    assert reason is None


def test_to_manifest():
    """State converts to manifest format correctly."""
    state = NegotiationState()
    state.round = 2
    state.add_turn("user", "test", 0.65)
    state.add_turn("assistant", "clarify?", 0.65)
    state.add_turn("user", "clarified", 0.85)
    state.terminated = True
    state.reason = "threshold_met"

    manifest = state.to_manifest()

    assert manifest["rounds"] == 2
    assert manifest["final_confidence"] == 0.85
    assert manifest["stopped_reason"] == "threshold_met"
    assert len(manifest["history"]) == 3
    assert len(manifest["deltas"]) == 2  # 3 turns = 2 deltas


# NegotiationManager Integration Tests (TODO)

@pytest.mark.skip(reason="Negotiation loop not yet implemented")
@pytest.mark.asyncio
async def test_negotiation_loop_threshold_met():
    """
    TODO: Negotiation loop stops when confidence crosses threshold.

    Scenario:
    - Initial: confidence=0.65, threshold=0.85
    - Round 1: Ask clarification, get response, confidence=0.88
    - Result: Stop with reason="threshold_met"
    """
    pass


@pytest.mark.skip(reason="Negotiation loop not yet implemented")
@pytest.mark.asyncio
async def test_negotiation_loop_max_rounds():
    """
    TODO: Negotiation loop stops at max rounds.

    Scenario:
    - Initial: confidence=0.65, threshold=0.85
    - Round 1: confidence=0.70
    - Round 2: confidence=0.75
    - Round 3: confidence=0.78
    - Result: Stop with reason="max_rounds"
    """
    pass


@pytest.mark.skip(reason="Negotiation loop not yet implemented")
@pytest.mark.asyncio
async def test_negotiation_loop_stagnation():
    """
    TODO: Negotiation loop stops on stagnation.

    Scenario:
    - Initial: confidence=0.65, threshold=0.85
    - Round 1: confidence=0.66 (delta=0.01)
    - Round 2: confidence=0.67 (delta=0.01)
    - Result: Stop with reason="stagnation"
    """
    pass


@pytest.mark.skip(reason="Negotiation loop not yet implemented")
@pytest.mark.asyncio
async def test_negotiation_context_update():
    """
    TODO: Negotiation loop updates context with clarifications.

    Verify that:
    - User clarifications are added to context
    - Re-matching uses updated context
    - Final match result includes all clarifications
    """
    pass


@pytest.mark.skip(reason="Negotiation loop not yet implemented")
@pytest.mark.asyncio
async def test_negotiation_manifest_recording():
    """
    TODO: Negotiation state is recorded in turn manifest.

    Verify manifest includes:
    - rounds: number of clarification rounds
    - final_confidence: final confidence score
    - stopped_reason: why negotiation ended
    - history: all turns (user + assistant)
    - deltas: confidence changes per round
    """
    pass

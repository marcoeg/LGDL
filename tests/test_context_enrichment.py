"""
Tests for context enrichment.

Tests ContextEnricher and context-aware pattern matching.
"""

import pytest
from datetime import datetime

from lgdl.runtime.context import ContextEnricher, EnrichedInput
from lgdl.runtime.state import PersistentState, Turn


@pytest.fixture
def enricher():
    """Create context enricher"""
    return ContextEnricher()


@pytest.fixture
def empty_state():
    """Create empty conversation state"""
    return PersistentState(
        conversation_id="test-123",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


@pytest.fixture
def state_with_history(empty_state):
    """Create state with conversation history"""
    # Add turns
    turn1 = Turn(
        turn_num=1,
        timestamp=datetime.utcnow(),
        user_input="I have pain",
        sanitized_input="I have pain",
        matched_move="pain_assessment",
        confidence=0.7,
        response="Where does it hurt?",
        extracted_params={"symptom": "pain"}
    )
    empty_state.add_turn(turn1)

    # Set awaiting response
    empty_state.awaiting_response = True
    empty_state.last_question = "Where does it hurt?"

    return empty_state


class TestContextEnricher:
    """Test context enrichment functionality"""

    def test_no_enrichment_for_empty_history(self, enricher, empty_state):
        """Test that no enrichment happens for new conversation"""
        result = enricher.enrich_input("Hello", empty_state)

        assert result.original_input == "Hello"
        assert result.enriched_input == "Hello"
        assert not result.enrichment_applied
        assert result.context_used == {}

    def test_enrich_with_previous_question(self, enricher, state_with_history):
        """Test enrichment based on previous question"""
        result = enricher.enrich_input("My chest", state_with_history)

        assert result.original_input == "My chest"
        assert "pain" in result.enriched_input.lower()
        assert "chest" in result.enriched_input.lower()
        assert result.enrichment_applied
        assert "last_question" in result.context_used

    def test_enrich_location_response(self, enricher):
        """Test enriching location response"""
        state = PersistentState(
            conversation_id="test",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            awaiting_response=True,
            last_question="Where does it hurt?"
        )

        result = enricher.enrich_input("my chest", state)

        assert "pain" in result.enriched_input.lower()
        assert "chest" in result.enriched_input

    def test_enrich_doctor_response(self, enricher):
        """Test enriching doctor name response"""
        state = PersistentState(
            conversation_id="test",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            awaiting_response=True,
            last_question="Which doctor do you want to see?"
        )

        result = enricher.enrich_input("Smith", state)

        assert "doctor" in result.enriched_input.lower() or "see" in result.enriched_input.lower()
        assert "Smith" in result.enriched_input

    def test_enrich_duration_response(self, enricher):
        """Test enriching duration/timeframe response"""
        state = PersistentState(
            conversation_id="test",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            awaiting_response=True,
            last_question="When did this pain start?"
        )

        result = enricher.enrich_input("one hour", state)

        assert "started" in result.enriched_input.lower() or "hour" in result.enriched_input

    def test_enrich_with_extracted_context(self, enricher):
        """Test enrichment with extracted context"""
        state = PersistentState(
            conversation_id="test",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            extracted_context={
                "symptom": "pain",
                "severity": "severe"
            }
        )

        turn = Turn(
            turn_num=1,
            timestamp=datetime.utcnow(),
            user_input="test",
            sanitized_input="test",
            matched_move="test",
            confidence=0.9,
            response="test"
        )
        state.add_turn(turn)

        result = enricher.enrich_input("in my back", state)

        # Should include symptom and severity
        assert "pain" in result.enriched_input.lower()
        assert "severe" in result.enriched_input.lower()
        assert "back" in result.enriched_input

    def test_no_duplication_of_context(self, enricher):
        """Test that context is not duplicated if already present"""
        state = PersistentState(
            conversation_id="test",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            extracted_context={"symptom": "pain"}
        )

        turn = Turn(
            turn_num=1,
            timestamp=datetime.utcnow(),
            user_input="test",
            sanitized_input="test",
            matched_move="test",
            confidence=0.9,
            response="test"
        )
        state.add_turn(turn)

        result = enricher.enrich_input("severe pain in chest", state)

        # Should not duplicate "pain"
        assert result.enriched_input.count("pain") == 1

    def test_extract_context_from_history(self, enricher):
        """Test extracting context from turn history"""
        turns = [
            Turn(
                turn_num=1,
                timestamp=datetime.utcnow(),
                user_input="I have pain",
                sanitized_input="I have pain",
                matched_move="pain_assessment",
                confidence=0.8,
                response="Where?",
                extracted_params={"symptom": "pain", "severity": "moderate"}
            ),
            Turn(
                turn_num=2,
                timestamp=datetime.utcnow(),
                user_input="In my chest",
                sanitized_input="In my chest",
                matched_move="pain_assessment",
                confidence=0.9,
                response="How long?",
                extracted_params={"location": "chest"}
            )
        ]

        context = enricher.extract_context_from_history(turns)

        assert context["symptom"] == "pain"
        assert context["severity"] == "moderate"
        assert context["location"] == "chest"
        assert "move_sequence" in context
        assert len(context["move_sequence"]) == 2

    def test_merge_contexts(self, enricher):
        """Test merging context dictionaries"""
        base = {"key1": "value1", "key2": "value2"}
        new = {"key2": "new_value2", "key3": "value3"}

        merged = enricher.merge_contexts(base, new)

        assert merged["key1"] == "value1"
        assert merged["key2"] == "new_value2"  # New value overwrites
        assert merged["key3"] == "value3"

    def test_merge_contexts_with_lists(self, enricher):
        """Test merging contexts with list values"""
        base = {"items": ["item1", "item2"]}
        new = {"items": ["item3"]}

        merged = enricher.merge_contexts(base, new)

        assert len(merged["items"]) == 3
        assert "item1" in merged["items"]
        assert "item3" in merged["items"]

    def test_get_recent_turns_context(self, enricher, state_with_history):
        """Test enrichment with recent turns"""
        # Add more turns
        for i in range(2, 5):
            turn = Turn(
                turn_num=i,
                timestamp=datetime.utcnow(),
                user_input=f"Input {i}",
                sanitized_input=f"Input {i}",
                matched_move="test_move",
                confidence=0.9,
                response=f"Response {i}",
                extracted_params={f"key{i}": f"value{i}"}
            )
            state_with_history.add_turn(turn)

        result = enricher.enrich_input("test input", state_with_history)

        # Should have access to recent turns context
        assert result.enrichment_applied

    def test_complex_multi_turn_enrichment(self, enricher):
        """Test complex multi-turn conversation enrichment"""
        state = PersistentState(
            conversation_id="test",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Turn 1: User reports pain
        turn1 = Turn(
            turn_num=1,
            timestamp=datetime.utcnow(),
            user_input="I have severe pain",
            sanitized_input="I have severe pain",
            matched_move="pain_assessment",
            confidence=0.7,
            response="Where does it hurt?",
            extracted_params={"symptom": "pain", "severity": "severe"}
        )
        state.add_turn(turn1)
        state.awaiting_response = True
        state.last_question = "Where does it hurt?"

        # Turn 2: User responds with location
        result = enricher.enrich_input("my chest", state)

        assert "pain" in result.enriched_input.lower()
        assert "severe" in result.enriched_input.lower()
        assert "chest" in result.enriched_input
        assert result.enrichment_applied

    def test_enrichment_preserves_original(self, enricher, state_with_history):
        """Test that enrichment preserves original input"""
        original = "my chest"
        result = enricher.enrich_input(original, state_with_history)

        assert result.original_input == original
        assert result.enriched_input != original  # Should be enriched

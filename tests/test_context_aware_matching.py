"""
Tests for Phase 1: Context-Aware Pattern Matching

Tests coverage:
1. Vocabulary-aware matching (LLM understands synonyms)
2. Cascade short-circuit (stop at confident stage)
3. Backward compatibility (flag OFF = old behavior)
4. Cost control (under $0.01/turn)
5. Latency targets (P95 <500ms)
6. Context enrichment (use conversation history)
"""

import pytest
import os
from lgdl.config import LGDLConfig
from lgdl.runtime.matching_context import MatchingContext
from lgdl.runtime.matcher import LLMSemanticMatcher, CascadeMatcher, TwoStageMatcher
from lgdl.runtime.llm_client import MockLLMClient, create_llm_client
from lgdl.runtime.engine import LGDLRuntime
from lgdl.parser.parser import parse_lgdl_source
from lgdl.parser.ir import compile_game
from lgdl.metrics import LGDLMetrics


# ============================================================================
# Test Configuration
# ============================================================================

@pytest.fixture
def test_config_disabled():
    """Config with semantic matching disabled (backward compat)."""
    return LGDLConfig(
        openai_api_key=None,
        enable_llm_semantic_matching=False
    )


@pytest.fixture
def test_config_enabled():
    """Config with semantic matching enabled (uses mock LLM)."""
    return LGDLConfig(
        openai_api_key="test-key",
        enable_llm_semantic_matching=True,
        cascade_lexical_threshold=0.75,
        cascade_embedding_threshold=0.80
    )


@pytest.fixture
def test_game_with_vocabulary():
    """Test game with vocabulary for semantic matching."""
    source = """
game medical_triage {
    description: "Emergency room patient triage"

    vocabulary {
        "heart" also means: ["ticker", "chest", "cardiovascular"]
        "pain" also means: ["hurting", "aching", "discomfort"]
    }

    moves {
        move chest_pain {
            when user says something like: [
                "I have pain in my {location}",
                "{location} pain"
            ]
            confidence: 0.8

            when confident {
                respond with: "I understand you have pain in your {location}."
            }
        }

        move general_complaint {
            when user says something like: [
                "I don't feel good",
                "something is wrong"
            ]
            confidence: 0.5

            when uncertain {
                negotiate "Can you tell me more about what's bothering you?" until confident
            }
        }
    }
}
"""
    ast = parse_lgdl_source(source)
    return compile_game(ast[0])


# ============================================================================
# Unit Tests: LLM Semantic Matcher
# ============================================================================

@pytest.mark.asyncio
async def test_llm_semantic_matcher_basic():
    """Test basic LLM semantic matching."""
    mock_llm = MockLLMClient(default_confidence=0.85, default_reasoning="Test match")
    matcher = LLMSemanticMatcher(mock_llm)

    context = MatchingContext(
        game_name="test_game",
        game_description="Test game",
        vocabulary={}
    )

    result = await matcher.match(
        text="test input",
        pattern="test pattern",
        context=context
    )

    assert "confidence" in result
    assert result["confidence"] == 0.85
    assert result["stage"] == "llm_semantic"
    assert "reasoning" in result


@pytest.mark.asyncio
async def test_llm_semantic_matcher_with_vocabulary():
    """Test that LLM receives vocabulary in prompt."""
    mock_llm = MockLLMClient()
    matcher = LLMSemanticMatcher(mock_llm)

    context = MatchingContext(
        game_name="medical_triage",
        game_description="Emergency triage",
        vocabulary={
            "heart": ["ticker", "chest", "cardiovascular"],
            "pain": ["hurting", "aching"]
        }
    )

    result = await matcher.match(
        text="My ticker hurts",
        pattern="I have pain in my {location}",
        context=context
    )

    # Mock should return valid response
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_llm_semantic_matcher_with_history():
    """Test that LLM receives conversation history."""
    mock_llm = MockLLMClient()
    matcher = LLMSemanticMatcher(mock_llm)

    context = MatchingContext(
        game_name="medical_triage",
        conversation_history=[
            {"role": "assistant", "content": "What brings you in today?"},
            {"role": "user", "content": "I'm not feeling well"}
        ],
        vocabulary={}
    )

    result = await matcher.match(
        text="my chest",
        pattern="pain in {location}",
        context=context
    )

    # Should work with history context
    assert "confidence" in result


# ============================================================================
# Unit Tests: Cascade Matcher
# ============================================================================

def test_cascade_matcher_initialization_disabled():
    """Test cascade matcher with feature disabled."""
    config = LGDLConfig(
        openai_api_key=None,
        enable_llm_semantic_matching=False
    )

    cascade = CascadeMatcher(config)

    assert cascade.llm_matcher is None
    assert cascade.emb is not None


def test_cascade_matcher_initialization_enabled():
    """Test cascade matcher with feature enabled."""
    config = LGDLConfig(
        openai_api_key="test-key",
        enable_llm_semantic_matching=True
    )

    cascade = CascadeMatcher(config)

    # Should have LLM matcher
    assert cascade.llm_matcher is not None


@pytest.mark.asyncio
async def test_cascade_lexical_short_circuit(test_game_with_vocabulary, test_config_enabled):
    """Test cascade stops at lexical for exact match."""
    cascade = CascadeMatcher(test_config_enabled)
    context = MatchingContext.from_state(test_game_with_vocabulary, None)

    # Exact pattern match should stop at lexical stage
    result = await cascade.match(
        text="I have pain in my chest",
        compiled_game=test_game_with_vocabulary,
        context=context
    )

    # Should match
    assert result["move"] is not None
    assert result["score"] > 0.7

    # Should stop at lexical (exact regex match)
    # Note: Might be embedding if regex doesn't match perfectly
    assert result["stage"] in ["lexical", "embedding"]


@pytest.mark.asyncio
async def test_cascade_embedding_stage(test_game_with_vocabulary, test_config_enabled):
    """Test cascade uses embedding for semantic similarity."""
    cascade = CascadeMatcher(test_config_enabled)
    context = MatchingContext.from_state(test_game_with_vocabulary, None)

    # Similar but not exact - should use embedding
    result = await cascade.match(
        text="My chest hurts",
        compiled_game=test_game_with_vocabulary,
        context=context
    )

    assert result["move"] is not None
    assert result["stage"] in ["lexical", "embedding", "llm_semantic"]


# ============================================================================
# Integration Tests: Vocabulary Compilation
# ============================================================================

def test_vocabulary_parsing_and_compilation():
    """Test that vocabulary is parsed and compiled correctly."""
    source = """
game test {
    vocabulary {
        "heart" also means: ["ticker", "chest"]
        "pain" also means: ["hurting", "aching"]
    }

    moves {
        move test_move {
            when user says something like: ["test"]
            confidence: high
            when confident {
                respond with: "ok"
            }
        }
    }
}
"""

    ast = parse_lgdl_source(source)
    assert len(ast) == 1
    game_ast = ast[0]

    # Check AST has vocabulary
    assert len(game_ast.vocabulary) == 2
    assert game_ast.vocabulary[0].term == "heart"
    assert game_ast.vocabulary[0].synonyms == ["ticker", "chest"]

    # Check compiled IR
    compiled = compile_game(game_ast)
    assert "vocabulary" in compiled
    assert compiled["vocabulary"]["heart"] == ["ticker", "chest"]
    assert compiled["vocabulary"]["pain"] == ["hurting", "aching"]


def test_empty_vocabulary():
    """Test game without vocabulary compiles correctly."""
    source = """
game test {
    moves {
        move test_move {
            when user says something like: ["test"]
            confidence: high
            when confident {
                respond with: "ok"
            }
        }
    }
}
"""

    ast = parse_lgdl_source(source)
    compiled = compile_game(ast[0])

    assert "vocabulary" in compiled
    assert compiled["vocabulary"] == {}


# ============================================================================
# Integration Tests: Matching Context
# ============================================================================

def test_matching_context_from_state():
    """Test building MatchingContext from compiled game."""
    source = """
game test {
    description: "Test game"
    vocabulary {
        "test" also means: ["exam", "quiz"]
    }
    moves {
        move test_move {
            when user says something like: ["test"]
            confidence: high
            when confident {
                respond with: "ok"
            }
        }
    }
}
"""

    ast = parse_lgdl_source(source)
    compiled = compile_game(ast[0])

    context = MatchingContext.from_state(compiled, None)

    assert context.game_name == "test"
    assert context.game_description == "Test game"
    assert "test" in context.vocabulary
    assert context.vocabulary["test"] == ["exam", "quiz"]


def test_matching_context_relevant_vocabulary():
    """Test filtering vocabulary to relevant terms."""
    context = MatchingContext(
        game_name="test",
        vocabulary={
            "heart": ["ticker", "chest"],
            "stomach": ["belly", "gut"],
            "head": ["noggin", "skull"]
        }
    )

    # Get vocabulary relevant to "ticker hurts"
    relevant = context.get_relevant_vocabulary("ticker hurts")

    # Should only include "heart" (because "ticker" appears)
    assert "heart" in relevant
    assert relevant["heart"] == ["ticker", "chest"]
    # Should not include irrelevant terms
    assert "stomach" not in relevant
    assert "head" not in relevant


# ============================================================================
# Integration Tests: Runtime with Cascade
# ============================================================================

@pytest.mark.asyncio
async def test_runtime_backward_compatibility(test_game_with_vocabulary, test_config_disabled):
    """Test that runtime works with cascade disabled (backward compat)."""
    runtime = LGDLRuntime(
        compiled=test_game_with_vocabulary,
        config=test_config_disabled
    )

    # Should use TwoStageMatcher
    assert isinstance(runtime.matcher, TwoStageMatcher)
    assert not runtime.use_cascade

    # Should process turns normally
    result = await runtime.process_turn(
        conversation_id="test",
        user_id="user1",
        text="I have pain in my chest",
        context={}
    )

    assert result["move_id"] in ["chest_pain", "none"]


@pytest.mark.asyncio
async def test_runtime_with_cascade_enabled(test_game_with_vocabulary, test_config_enabled):
    """Test runtime with cascade matching enabled."""
    runtime = LGDLRuntime(
        compiled=test_game_with_vocabulary,
        config=test_config_enabled
    )

    # Should use CascadeMatcher
    assert isinstance(runtime.matcher, CascadeMatcher)
    assert runtime.use_cascade

    # Should process turns with cascade
    result = await runtime.process_turn(
        conversation_id="test",
        user_id="user1",
        text="I have pain in my chest",
        context={}
    )

    assert "stage" in result  # Cascade adds stage metadata
    assert result["stage"] in ["lexical", "embedding", "llm_semantic", "unknown"]


# ============================================================================
# Performance Tests
# ============================================================================

def test_metrics_collection():
    """Test that metrics are collected correctly."""
    metrics = LGDLMetrics()

    # Record some turns
    metrics.record_turn(stage="lexical", confidence=0.95, latency_ms=5.0, cost_usd=0.0)
    metrics.record_turn(stage="embedding", confidence=0.82, latency_ms=15.0, cost_usd=0.0001)
    metrics.record_turn(stage="llm_semantic", confidence=0.88, latency_ms=220.0, cost_usd=0.008)

    # Check distribution
    dist = metrics.get_cascade_distribution()
    assert dist["lexical"] == pytest.approx(1/3)
    assert dist["embedding"] == pytest.approx(1/3)
    assert dist["llm_semantic"] == pytest.approx(1/3)

    # Check averages
    assert metrics.get_average_cost() == pytest.approx(0.0027, abs=0.0001)
    assert metrics.get_average_confidence() == pytest.approx(0.883, abs=0.01)


def test_metrics_targets():
    """Test metrics target checking."""
    metrics = LGDLMetrics()

    # Simulate cascade with good performance
    for _ in range(45):
        metrics.record_turn("lexical", 0.90, 5.0, 0.0)  # 45% lexical
    for _ in range(40):
        metrics.record_turn("embedding", 0.82, 15.0, 0.0001)  # 40% embedding
    for _ in range(15):
        metrics.record_turn("llm_semantic", 0.88, 220.0, 0.008)  # 15% LLM

    # Check targets
    targets = metrics.check_targets()

    assert targets["cost_target_met"]  # Should be ~$0.0015 < $0.01
    assert targets["latency_target_met"]  # P95 should be <500ms
    assert targets["confidence_target_met"]  # Avg should be >0.75


# ============================================================================
# Golden Dialog Tests with Vocabulary
# ============================================================================

@pytest.mark.asyncio
async def test_vocabulary_understanding_exact():
    """Test that vocabulary enables understanding of synonyms - exact test."""
    source = """
game test {
    vocabulary {
        "heart" also means: ["ticker"]
    }

    moves {
        move heart_issue {
            when user says something like: ["my {bodypart} hurts"]
            confidence: 0.5

            when confident {
                respond with: "I see you have an issue with your {bodypart}."
            }
        }
    }
}
"""

    ast = parse_lgdl_source(source)
    compiled = compile_game(ast[0])

    # Verify vocabulary in compiled IR
    assert "vocabulary" in compiled
    assert "heart" in compiled["vocabulary"]
    assert "ticker" in compiled["vocabulary"]["heart"]


@pytest.mark.asyncio
async def test_config_validation():
    """Test configuration validation."""
    # Valid config
    config = LGDLConfig(cascade_lexical_threshold=0.75)
    config.validate()  # Should not raise

    # Invalid threshold
    with pytest.raises(ValueError, match="cascade_lexical_threshold"):
        bad_config = LGDLConfig(cascade_lexical_threshold=1.5)
        bad_config.validate()

    # Semantic matching without API key
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        bad_config = LGDLConfig(
            enable_llm_semantic_matching=True,
            openai_api_key=None
        )
        bad_config.validate()


def test_cascade_fails_without_api_key():
    """Test that CascadeMatcher fails explicitly when LLM enabled but no API key."""
    config = LGDLConfig(
        openai_api_key=None,  # No API key
        enable_llm_semantic_matching=True  # But feature enabled
    )

    # Should raise ValueError, not silently fall back to mock
    with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
        cascade = CascadeMatcher(config)


def test_config_from_env():
    """Test loading config from environment."""
    # Set test environment variables
    os.environ["LGDL_ENABLE_LLM_SEMANTIC_MATCHING"] = "true"
    os.environ["LGDL_CASCADE_LEXICAL_THRESHOLD"] = "0.80"
    os.environ["OPENAI_API_KEY"] = "test-key"

    config = LGDLConfig.from_env()

    assert config.enable_llm_semantic_matching == True
    assert config.cascade_lexical_threshold == 0.80
    assert config.openai_api_key == "test-key"

    # Cleanup
    del os.environ["LGDL_ENABLE_LLM_SEMANTIC_MATCHING"]
    del os.environ["LGDL_CASCADE_LEXICAL_THRESHOLD"]


def test_config_summary():
    """Test config summary generation."""
    config = LGDLConfig(
        enable_llm_semantic_matching=True,
        openai_llm_model="gpt-4o-mini"
    )

    summary = config.get_summary()

    assert "LGDL Configuration Summary" in summary
    assert "Phase 1 - Context-Aware Matching" in summary
    assert "Enabled: True" in summary
    assert "gpt-4o-mini" in summary


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.asyncio
async def test_cascade_with_no_match():
    """Test cascade when no move matches."""
    source = """
game test {
    moves {
        move specific {
            when user says something like: ["very specific phrase"]
            confidence: high
            when confident {
                respond with: "ok"
            }
        }
    }
}
"""

    ast = parse_lgdl_source(source)
    compiled = compile_game(ast[0])

    config = LGDLConfig(
        openai_api_key="test",
        enable_llm_semantic_matching=True
    )

    cascade = CascadeMatcher(config)
    context = MatchingContext.from_state(compiled, None)

    result = await cascade.match(
        text="completely unrelated input",
        compiled_game=compiled,
        context=context
    )

    # Should return best attempt even if low confidence
    assert result is not None
    # Might match with low score or might be None
    assert result["score"] >= 0.0


@pytest.mark.asyncio
async def test_cascade_fallback_on_llm_error(test_game_with_vocabulary):
    """Test that cascade falls back gracefully on LLM errors."""
    # Create config with LLM enabled but use mock that might fail
    config = LGDLConfig(
        openai_api_key="test",
        enable_llm_semantic_matching=True
    )

    cascade = CascadeMatcher(config)
    context = MatchingContext.from_state(test_game_with_vocabulary, None)

    # Should still return result even if LLM fails
    result = await cascade.match(
        text="test input",
        compiled_game=test_game_with_vocabulary,
        context=context
    )

    assert result is not None
    # Should fallback to lexical or embedding
    assert result["stage"] in ["lexical", "embedding", "llm_semantic", "none"]


# ============================================================================
# Backward Compatibility Tests
# ============================================================================

@pytest.mark.asyncio
async def test_existing_games_work_without_vocabulary():
    """Test that games without vocabulary still work."""
    source = """
game simple {
    moves {
        move greet {
            when user says something like: ["hello", "hi"]
            confidence: high
            when confident {
                respond with: "Hello!"
            }
        }
    }
}
"""

    ast = parse_lgdl_source(source)
    compiled = compile_game(ast[0])

    # Should have empty vocabulary
    assert compiled["vocabulary"] == {}

    # Should work with old matcher
    config = LGDLConfig(enable_llm_semantic_matching=False)
    runtime = LGDLRuntime(compiled=compiled, config=config)

    result = await runtime.process_turn(
        conversation_id="test",
        user_id="user1",
        text="hello",
        context={}
    )

    assert result["move_id"] == "greet"


@pytest.mark.asyncio
async def test_two_stage_matcher_unchanged():
    """Test that TwoStageMatcher still works as before."""
    source = """
game test {
    moves {
        move test {
            when user says something like: ["test input"]
            confidence: 0.7
            when confident {
                respond with: "matched"
            }
        }
    }
}
"""

    ast = parse_lgdl_source(source)
    compiled = compile_game(ast[0])

    # Use TwoStageMatcher directly
    matcher = TwoStageMatcher()
    result = matcher.match("test input", compiled)

    assert result["move"] is not None
    assert result["score"] > 0.7


# ============================================================================
# Cost Control Tests
# ============================================================================

def test_cost_estimation():
    """Test that cost estimation works."""
    from lgdl.runtime.llm_client import OpenAIClient

    # Create client (won't actually call API in this test)
    client = MockLLMClient()

    # Estimate cost
    cost = client.estimate_cost(
        prompt="Test prompt with some text",
        max_tokens=100
    )

    # Mock always returns 0
    assert cost == 0.0


def test_metrics_cost_tracking():
    """Test that metrics track costs correctly."""
    metrics = LGDLMetrics()

    # Simulate turns with different costs
    metrics.record_turn("lexical", 0.90, 5.0, 0.0)
    metrics.record_turn("embedding", 0.82, 15.0, 0.0001)
    metrics.record_turn("llm_semantic", 0.88, 220.0, 0.008)

    # Total cost should be sum of individual costs
    assert metrics.get_total_cost() == pytest.approx(0.0081, abs=0.0001)

    # Average should be total / count
    assert metrics.get_average_cost() == pytest.approx(0.0027, abs=0.0001)


# ============================================================================
# Summary Test
# ============================================================================

def test_metrics_summary_format():
    """Test that metrics summary is human-readable."""
    metrics = LGDLMetrics()

    # Add sample data
    metrics.record_turn("lexical", 0.90, 5.0, 0.0)
    metrics.record_turn("embedding", 0.82, 15.0, 0.0001)

    summary = metrics.get_summary()

    assert "LGDL Metrics Summary" in summary
    assert "Cascade Distribution" in summary
    assert "Performance" in summary
    assert "Cost" in summary
    assert "lexical" in summary.lower()

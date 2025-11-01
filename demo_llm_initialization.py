#!/usr/bin/env python3
"""
Demonstrate LLM initialization behavior - explicit failure vs success.

Shows:
1. LLM DISABLED: Works fine (backward compatible)
2. LLM ENABLED without API key: FAILS explicitly (no guessing)
3. LLM ENABLED with API key: Works with clear logging
"""

import os
import sys
from lgdl.config import LGDLConfig
from lgdl.runtime.matcher import CascadeMatcher
from lgdl.parser.parser import parse_lgdl_source
from lgdl.parser.ir import compile_game


def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


# Create a simple test game
source = """
game test {
    vocabulary {
        "heart" also means: ["ticker", "chest"]
    }

    moves {
        move test {
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

# ============================================================================
# Scenario 1: LLM DISABLED (default, backward compatible)
# ============================================================================

print_section("Scenario 1: LLM DISABLED (Default Behavior)")

config1 = LGDLConfig(
    openai_api_key=None,  # No API key
    enable_llm_semantic_matching=False  # Feature disabled
)

print("Config:")
print(f"  enable_llm_semantic_matching: {config1.enable_llm_semantic_matching}")
print(f"  openai_api_key: {config1.openai_api_key}")

try:
    cascade1 = CascadeMatcher(config1)
    print("\n✅ SUCCESS: CascadeMatcher created")
    print("   → Uses TwoStageMatcher (backward compatible)")
    print("   → No LLM calls will be made")
except Exception as e:
    print(f"\n❌ FAILED: {e}")


# ============================================================================
# Scenario 2: LLM ENABLED but NO API KEY (should fail explicitly)
# ============================================================================

print_section("Scenario 2: LLM ENABLED but NO API KEY")

config2 = LGDLConfig(
    openai_api_key=None,  # No API key!
    enable_llm_semantic_matching=True  # But feature enabled!
)

print("Config:")
print(f"  enable_llm_semantic_matching: {config2.enable_llm_semantic_matching}")
print(f"  openai_api_key: {config2.openai_api_key}")

print("\nAttempting to create CascadeMatcher...")

try:
    cascade2 = CascadeMatcher(config2)
    print("\n❌ UNEXPECTED: Should have failed but didn't!")
    print("   → This is a bug - should require API key")
except ValueError as e:
    print(f"\n✅ SUCCESS: Failed explicitly (as expected)")
    print(f"   Error message: {e}")
    print("   → Clear error, no silent fallback, no guessing")
except Exception as e:
    print(f"\n⚠️  FAILED with unexpected error: {e}")


# ============================================================================
# Scenario 3: LLM ENABLED with API KEY (should work with logging)
# ============================================================================

print_section("Scenario 3: LLM ENABLED with API KEY")

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("⚠️  OPENAI_API_KEY not set in environment")
    print("   Run: source ~/.env")
    print("   Skipping this scenario...")
else:
    config3 = LGDLConfig(
        openai_api_key=api_key,
        enable_llm_semantic_matching=True,
        cascade_lexical_threshold=0.75,
        cascade_embedding_threshold=0.80,
        openai_llm_model="gpt-4o-mini"
    )

    print("Config:")
    print(f"  enable_llm_semantic_matching: {config3.enable_llm_semantic_matching}")
    print(f"  openai_api_key: {api_key[:15]}...")
    print(f"  openai_llm_model: {config3.openai_llm_model}")
    print(f"  cascade_lexical_threshold: {config3.cascade_lexical_threshold}")
    print(f"  cascade_embedding_threshold: {config3.cascade_embedding_threshold}")

    print("\nCreating CascadeMatcher...")

    try:
        cascade3 = CascadeMatcher(config3)
        print("\n✅ SUCCESS: CascadeMatcher created with REAL LLM")
        print("   → LLM semantic matching is ENABLED")
        print("   → Will use OpenAI API for complex cases")
        print("   → Cascade will optimize cost (lexical → embedding → LLM)")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# Summary
# ============================================================================

print_section("Summary")

print("✅ LLM initialization behavior is EXPLICIT and SAFE:")
print()
print("1. Feature DISABLED + No API key:")
print("   → Works fine (backward compatible)")
print()
print("2. Feature ENABLED + No API key:")
print("   → FAILS with clear error message")
print("   → No silent fallback to mock")
print("   → No guessing or assuming")
print()
print("3. Feature ENABLED + API key present:")
print("   → Works with clear logging")
print("   → Shows model, thresholds, status")
print("   → Ready for production use")
print()
print("This prevents silent failures in production!")

"""
LGDL Configuration Module

Centralized configuration for LGDL runtime with feature flags for semantic enhancements.
Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class LGDLConfig:
    """Configuration for LGDL runtime and semantic enhancements.

    This class consolidates all configuration options including:
    - Existing embedding configuration
    - Phase 1: Context-aware LLM semantic matching
    - Phase 2: Semantic slot extraction (future)
    - Phase 3: Learning engine (future)

    All features are opt-in via feature flags (default OFF for backward compatibility).
    """

    # ====================
    # Existing Configuration (migrated from env vars)
    # ====================

    openai_api_key: Optional[str] = None
    """OpenAI API key for embeddings and LLM calls"""

    embedding_model: str = "text-embedding-3-small"
    """OpenAI embedding model"""

    embedding_version: str = "2025-01"
    """Embedding version for cache key stability"""

    embedding_cache_enabled: bool = True
    """Enable SQLite caching of embeddings"""

    # ====================
    # Phase 1: Context-Aware Semantic Matching (NEW)
    # ====================

    enable_llm_semantic_matching: bool = False
    """Enable context-aware LLM semantic matching (Phase 1 feature).

    When enabled, uses cascade strategy:
      1. Lexical (regex) - free, <1ms
      2. Embedding - cached, ~$0.0001/turn
      3. LLM Semantic - context-aware, ~$0.01/turn

    Default: False (backward compatible)
    """

    cascade_lexical_threshold: float = 0.75
    """Confidence threshold for lexical stage.

    If lexical matching achieves confidence >= this threshold,
    cascade stops early (no embedding or LLM needed).

    Default: 0.75 (stop if 75%+ confident from regex)
    """

    cascade_embedding_threshold: float = 0.80
    """Confidence threshold for embedding stage.

    If embedding matching achieves confidence >= this threshold,
    cascade stops before LLM stage.

    Default: 0.80 (stop if 80%+ confident from embeddings)
    """

    openai_llm_model: str = "gpt-4o-mini"
    """OpenAI model for semantic matching.

    Default: gpt-4o-mini (cost-effective, fast)
    Alternatives: gpt-4o, gpt-3.5-turbo
    """

    llm_max_tokens: int = 100
    """Maximum tokens for LLM completions.

    Semantic matching only needs short responses (confidence + reasoning).
    Keeping this low controls costs.
    """

    llm_temperature: float = 0.0
    """LLM temperature for deterministic outputs.

    0.0 = deterministic (same input → same output)
    Recommended for pattern matching to ensure consistency.
    """

    max_cost_per_turn: float = 0.01
    """Maximum cost per conversation turn (circuit breaker).

    If estimated cost exceeds this, system falls back to embeddings.
    Default: $0.01 (well above typical ~$0.0015 with cascade)
    """

    # ====================
    # Phase 2: Semantic Slot Extraction (Future)
    # ====================

    enable_semantic_slot_extraction: bool = False
    """Enable semantic slot extraction (Phase 2 feature).

    When enabled, slots can use 'extraction: semantic' for
    natural language understanding beyond regex.

    Default: False (not yet implemented)
    """

    # ====================
    # Phase 3: Learning Engine (Future)
    # ====================

    enable_learning: bool = False
    """Enable pattern learning from successful interactions (Phase 3).

    When enabled, system proposes new patterns based on successful
    negotiations. All proposals require human review before deployment.

    Default: False (not yet implemented)
    """

    learning_min_frequency: int = 3
    """Minimum occurrences before proposing a pattern.

    Prevents noise from one-off phrasings.
    """

    learning_shadow_test_size: int = 1000
    """Number of historical conversations for shadow testing.

    Proposed patterns are tested on this many past conversations
    to detect regressions before human review.
    """

    learning_confidence_boost: float = 0.05
    """Confidence adjustment per successful/failed interaction.

    Patterns that succeed get +0.05 confidence boost.
    Patterns that fail get -0.05 confidence reduction.
    """

    learning_similarity_threshold: float = 0.8
    """Similarity threshold for finding related patterns.

    Used to determine if a proposed pattern is similar to existing ones.
    Range: 0.0 (no similarity) to 1.0 (identical).
    """

    # ====================
    # Runtime Configuration
    # ====================

    negotiation_enabled: bool = True
    """Enable clarification loop for uncertain matches"""

    negotiation_max_rounds: int = 3
    """Maximum negotiation rounds before escalation"""

    negotiation_epsilon: float = 0.05
    """Confidence improvement threshold for convergence"""

    state_disabled: bool = False
    """Disable state persistence (for testing)"""

    test_mode: bool = False
    """Auto-select first option in negotiation (for testing)"""

    @classmethod
    def from_env(cls) -> "LGDLConfig":
        """Load configuration from environment variables.

        Environment variables:
          OPENAI_API_KEY - OpenAI API key
          OPENAI_EMBEDDING_MODEL - Embedding model name
          OPENAI_EMBEDDING_VERSION - Version for cache stability
          EMBEDDING_CACHE - Enable/disable cache (1/0)

          LGDL_ENABLE_LLM_SEMANTIC_MATCHING - Enable Phase 1 (true/false)
          LGDL_CASCADE_LEXICAL_THRESHOLD - Lexical threshold (0.0-1.0)
          LGDL_CASCADE_EMBEDDING_THRESHOLD - Embedding threshold (0.0-1.0)
          OPENAI_LLM_MODEL - LLM model name
          LGDL_MAX_COST_PER_TURN - Cost circuit breaker

          LGDL_ENABLE_SEMANTIC_SLOT_EXTRACTION - Enable Phase 2 (future)
          LGDL_ENABLE_LEARNING - Enable Phase 3 (future)

          LGDL_NEGOTIATION - Enable negotiation (1/0)
          LGDL_NEGOTIATION_MAX_ROUNDS - Max rounds
          LGDL_NEGOTIATION_EPSILON - Convergence threshold
          LGDL_STATE_DISABLED - Disable state (1/0)
          LGDL_TEST_MODE - Test mode (1/0)

        Returns:
            LGDLConfig instance with values from environment
        """
        return cls(
            # Existing configuration
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_version=os.getenv("OPENAI_EMBEDDING_VERSION", "2025-01"),
            embedding_cache_enabled=os.getenv("EMBEDDING_CACHE", "1") == "1",

            # Phase 1: Context-aware matching
            enable_llm_semantic_matching=os.getenv(
                "LGDL_ENABLE_LLM_SEMANTIC_MATCHING", "false"
            ).lower() == "true",
            cascade_lexical_threshold=float(
                os.getenv("LGDL_CASCADE_LEXICAL_THRESHOLD", "0.75")
            ),
            cascade_embedding_threshold=float(
                os.getenv("LGDL_CASCADE_EMBEDDING_THRESHOLD", "0.80")
            ),
            openai_llm_model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"),
            llm_max_tokens=int(os.getenv("LGDL_LLM_MAX_TOKENS", "100")),
            llm_temperature=float(os.getenv("LGDL_LLM_TEMPERATURE", "0.0")),
            max_cost_per_turn=float(os.getenv("LGDL_MAX_COST_PER_TURN", "0.01")),

            # Phase 2: Semantic extraction (future)
            enable_semantic_slot_extraction=os.getenv(
                "LGDL_ENABLE_SEMANTIC_SLOT_EXTRACTION", "false"
            ).lower() == "true",

            # Phase 3: Learning (future)
            enable_learning=os.getenv("LGDL_ENABLE_LEARNING", "false").lower() == "true",
            learning_min_frequency=int(os.getenv("LGDL_LEARNING_MIN_FREQUENCY", "3")),
            learning_shadow_test_size=int(os.getenv("LGDL_LEARNING_SHADOW_TEST_SIZE", "1000")),
            learning_confidence_boost=float(os.getenv("LGDL_LEARNING_CONFIDENCE_BOOST", "0.05")),
            learning_similarity_threshold=float(os.getenv("LGDL_LEARNING_SIMILARITY_THRESHOLD", "0.8")),

            # Runtime configuration
            negotiation_enabled=os.getenv("LGDL_NEGOTIATION", "1") == "1",
            negotiation_max_rounds=int(os.getenv("LGDL_NEGOTIATION_MAX_ROUNDS", "3")),
            negotiation_epsilon=float(os.getenv("LGDL_NEGOTIATION_EPSILON", "0.05")),
            state_disabled=os.getenv("LGDL_STATE_DISABLED", "0") == "1",
            test_mode=os.getenv("LGDL_TEST_MODE", "0") == "1",
        )

    def validate(self) -> None:
        """Validate configuration settings.

        Raises:
            ValueError: If configuration is invalid
        """
        # Validate thresholds
        if not (0.0 <= self.cascade_lexical_threshold <= 1.0):
            raise ValueError(
                f"cascade_lexical_threshold must be 0.0-1.0, got {self.cascade_lexical_threshold}"
            )

        if not (0.0 <= self.cascade_embedding_threshold <= 1.0):
            raise ValueError(
                f"cascade_embedding_threshold must be 0.0-1.0, got {self.cascade_embedding_threshold}"
            )

        if not (0.0 <= self.llm_temperature <= 2.0):
            raise ValueError(
                f"llm_temperature must be 0.0-2.0, got {self.llm_temperature}"
            )

        # Validate semantic features require API key
        if self.enable_llm_semantic_matching and not self.openai_api_key:
            raise ValueError(
                "enable_llm_semantic_matching=True requires OPENAI_API_KEY"
            )

        if self.enable_semantic_slot_extraction and not self.openai_api_key:
            raise ValueError(
                "enable_semantic_slot_extraction=True requires OPENAI_API_KEY"
            )

        # Validate cost limits
        if self.max_cost_per_turn <= 0:
            raise ValueError(
                f"max_cost_per_turn must be positive, got {self.max_cost_per_turn}"
            )

        # Validate negotiation settings
        if self.negotiation_max_rounds < 1:
            raise ValueError(
                f"negotiation_max_rounds must be >= 1, got {self.negotiation_max_rounds}"
            )

    def get_summary(self) -> str:
        """Get human-readable configuration summary.

        Returns:
            Formatted string describing current configuration
        """
        lines = [
            "LGDL Configuration Summary",
            "=" * 50,
            "",
            "Embeddings:",
            f"  Model: {self.embedding_model}",
            f"  Cache: {'Enabled' if self.embedding_cache_enabled else 'Disabled'}",
            f"  API Key: {'Set' if self.openai_api_key else 'Not set'}",
            "",
            "Phase 1 - Context-Aware Matching:",
            f"  Enabled: {self.enable_llm_semantic_matching}",
        ]

        if self.enable_llm_semantic_matching:
            lines.extend([
                f"  LLM Model: {self.openai_llm_model}",
                f"  Lexical Threshold: {self.cascade_lexical_threshold}",
                f"  Embedding Threshold: {self.cascade_embedding_threshold}",
                f"  Max Cost/Turn: ${self.max_cost_per_turn}",
            ])

        lines.extend([
            "",
            "Phase 2 - Semantic Extraction:",
            f"  Enabled: {self.enable_semantic_slot_extraction}",
            "",
            "Phase 3 - Learning:",
            f"  Enabled: {self.enable_learning}",
            "",
            "Runtime:",
            f"  Negotiation: {'Enabled' if self.negotiation_enabled else 'Disabled'}",
            f"  State: {'Disabled' if self.state_disabled else 'Enabled'}",
            f"  Test Mode: {self.test_mode}",
        ])

        return "\n".join(lines)


# Default configuration instance (lazy-loaded from environment)
_default_config: Optional[LGDLConfig] = None


def get_default_config() -> LGDLConfig:
    """Get default configuration instance (singleton pattern).

    Returns:
        Default LGDLConfig loaded from environment
    """
    global _default_config
    if _default_config is None:
        _default_config = LGDLConfig.from_env()
        _default_config.validate()
    return _default_config

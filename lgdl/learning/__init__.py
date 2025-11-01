"""
LGDL Learning Engine - Phase 3

Implements Wittgensteinian "meaning through use" - learns patterns from successful
interactions with propose-only safety.

CRITICAL SAFETY PRINCIPLE:
    The system PROPOSES patterns, humans APPROVE them.
    NEVER auto-deploy learned patterns.

Core components:
- LearningEngine: Discovers patterns from successful interactions
- PatternDatabase: Tracks pattern performance over time
- ShadowTester: Tests proposals on historical data (regression detection)
- ReviewWorkflow: Human-in-loop approval process

Philosophy:
    "The meaning of a word is its use in the language."
    - Ludwig Wittgenstein, Philosophical Investigations

    Patterns emerge from successful use, not predefined rules.
    Human oversight ensures quality and safety.
"""

# Import classes for external use
from .engine import (
    LearningEngine,
    PatternDatabase,
    Interaction,
    PatternProposal,
    ProposalStatus,
    ProposalSource,
    ConfidenceAdjustment,
    VocabularyExpansion
)
from .shadow_test import ShadowTester, ShadowTestResults
from .review import ReviewWorkflow

__all__ = [
    "LearningEngine",
    "PatternDatabase",
    "Interaction",
    "PatternProposal",
    "ProposalStatus",
    "ProposalSource",
    "ConfidenceAdjustment",
    "VocabularyExpansion",
    "ShadowTester",
    "ShadowTestResults",
    "ReviewWorkflow",
]

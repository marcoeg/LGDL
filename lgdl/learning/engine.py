"""
LGDL Learning Engine - Core Implementation

Implements "meaning through use" - patterns learned from successful interactions.

CRITICAL SAFETY: Propose-only mode
- Patterns discovered from use
- Shadow tested on historical data
- Human review required before deployment
- Never auto-deploy

Philosophy: Wittgensteinian AI that learns what works in practice.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class ProposalStatus(Enum):
    """Status of a pattern proposal."""
    PENDING = "pending"           # Awaiting review
    SHADOW_TESTING = "shadow"     # Being tested on historical data
    AB_TESTING = "ab_test"        # Live A/B test
    APPROVED = "approved"         # Approved and deployed
    REJECTED = "rejected"         # Rejected by reviewer
    REVERTED = "reverted"         # Was approved but caused issues


class ProposalSource(Enum):
    """How a pattern was discovered."""
    NEGOTIATION_SUCCESS = "negotiation"  # From successful clarification
    USER_VARIATION = "variation"         # User phrased differently
    CLUSTERING = "clustering"            # Similar to existing patterns
    VOCABULARY_EXPANSION = "vocabulary"  # New synonym discovered


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class Interaction:
    """Record of a single conversation turn for learning.

    Captures all data needed to learn from an interaction:
    - What the user said
    - What pattern matched
    - How confident we were
    - What action we took
    - Whether it succeeded or failed
    - If we negotiated, how it resolved
    """
    timestamp: datetime
    conversation_id: str
    user_input: str
    matched_pattern: Optional[str]
    matched_move: Optional[str]
    confidence: float
    action_taken: str  # "respond", "negotiate", "escalate"
    outcome: str  # "success", "failure", "negotiation"
    negotiation_rounds: int = 0
    final_understanding: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternProposal:
    """Proposed pattern learned from use.

    SAFETY: All proposals start with status=PENDING.
    Requires explicit human approval to reach APPROVED status.
    """
    proposal_id: str
    pattern_text: str
    move_name: str
    source: ProposalSource
    source_interactions: List[Interaction]
    similar_to: Optional[str]  # Existing pattern this resembles

    # Evidence metrics
    frequency: int  # How many times seen
    success_rate: float  # % that led to successful completion
    confidence_boost: float  # Estimated confidence increase

    # Review metadata
    status: ProposalStatus
    created_at: datetime
    reviewed_by: Optional[str] = None
    review_timestamp: Optional[datetime] = None
    review_notes: Optional[str] = None

    # Testing results
    shadow_test_results: Optional[Dict[str, Any]] = None
    ab_test_results: Optional[Dict[str, Any]] = None


@dataclass
class ConfidenceAdjustment:
    """Record of confidence adjustment for a pattern."""
    pattern_text: str
    move_name: str
    adjustment: float  # Delta (+0.05 for success, -0.05 for failure)
    reason: str
    timestamp: datetime
    interaction_id: str


@dataclass
class VocabularyExpansion:
    """Proposed vocabulary addition discovered from use."""
    canonical_term: str
    discovered_synonym: str
    evidence: List[Interaction]
    confidence: float
    status: ProposalStatus
    created_at: datetime


# ============================================================================
# Pattern Database
# ============================================================================

class PatternDatabase:
    """Stores patterns and their performance history.

    Tracks how often patterns match, success rates, confidence scores.
    Used to identify successful patterns and propose improvements.
    """

    def __init__(self):
        """Initialize pattern database."""
        self.patterns: Dict[str, Dict[str, Any]] = {}
        self.pattern_history: List[Dict[str, Any]] = []

    def record_pattern_use(
        self,
        pattern_text: str,
        move_name: str,
        confidence: float,
        outcome: str,
        interaction: Interaction
    ):
        """Record that a pattern was used.

        Updates pattern statistics for learning.

        Args:
            pattern_text: The pattern that matched
            move_name: Move it matched to
            confidence: Match confidence
            outcome: "success", "failure", or "negotiation"
            interaction: Full interaction record
        """
        key = self._pattern_key(pattern_text, move_name)

        if key not in self.patterns:
            self.patterns[key] = {
                "pattern_text": pattern_text,
                "move_name": move_name,
                "uses": 0,
                "successes": 0,
                "failures": 0,
                "confidence_history": [],
                "success_rate": 0.0
            }

        pattern = self.patterns[key]
        pattern["uses"] += 1

        if outcome == "success":
            pattern["successes"] += 1
        elif outcome == "failure":
            pattern["failures"] += 1

        pattern["confidence_history"].append(confidence)
        pattern["success_rate"] = pattern["successes"] / pattern["uses"] if pattern["uses"] > 0 else 0.0

        # Record in history
        self.pattern_history.append({
            "timestamp": interaction.timestamp,
            "pattern_text": pattern_text,
            "move_name": move_name,
            "confidence": confidence,
            "outcome": outcome,
            "interaction_id": interaction.conversation_id
        })

    def get_pattern_performance(
        self,
        pattern_text: str,
        move_name: str
    ) -> Dict[str, Any]:
        """Get performance metrics for a pattern.

        Returns:
            Dict with uses, successes, failures, success_rate, confidence_history
        """
        key = self._pattern_key(pattern_text, move_name)
        return self.patterns.get(key, {})

    def find_similar_patterns(
        self,
        pattern_text: str,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Find patterns similar to given text.

        Args:
            pattern_text: Text to compare against
            threshold: Similarity threshold (0.0-1.0)

        Returns:
            List of similar patterns with metadata
        """
        similar = []
        for key, pattern in self.patterns.items():
            similarity = self._text_similarity(pattern_text, pattern["pattern_text"])
            if similarity >= threshold:
                similar.append({
                    **pattern,
                    "similarity": similarity
                })

        return sorted(similar, key=lambda x: x["similarity"], reverse=True)

    def _pattern_key(self, pattern_text: str, move_name: str) -> str:
        """Generate unique key for pattern."""
        return hashlib.md5(f"{move_name}:{pattern_text}".encode()).hexdigest()

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Compute text similarity (simple word overlap).

        Args:
            text1, text2: Texts to compare

        Returns:
            Similarity score 0.0-1.0 (Jaccard similarity)
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0


# ============================================================================
# Learning Engine
# ============================================================================

class LearningEngine:
    """Main engine for pattern learning from successful interactions.

    SAFETY GUARANTEE: Propose-only mode
    - Patterns proposed with status=PENDING
    - Shadow tested before review
    - Human approval required
    - Never auto-deployed

    Example workflow:
        1. User: "My ticker hurts" → Low confidence → Negotiate
        2. Clarified: "chest pain" → Success
        3. System proposes: "My {body_part} is bothering me"
        4. Shadow test on 1000 conversations
        5. Human reviews → Approves/Rejects
        6. If approved → Deploy to patterns
    """

    def __init__(
        self,
        pattern_db: PatternDatabase,
        embedding_client=None,
        llm_client=None,
        config=None
    ):
        """Initialize learning engine.

        Args:
            pattern_db: PatternDatabase for tracking performance
            embedding_client: For similarity computation
            llm_client: For proposal analysis and vocabulary discovery
            config: LGDLConfig with learning settings
        """
        self.pattern_db = pattern_db
        self.embedding = embedding_client
        self.llm = llm_client

        # Configuration
        from ..config import LGDLConfig
        self.config = config if config else LGDLConfig.from_env()

        # Storage
        self.proposals: List[PatternProposal] = []
        self.confidence_adjustments: List[ConfidenceAdjustment] = []
        self.vocabulary_proposals: List[VocabularyExpansion] = []

    async def learn_from_interaction(self, interaction: Interaction):
        """Process an interaction for learning opportunities.

        Main entry point for learning. Called after each conversation turn.

        Args:
            interaction: Complete interaction record with outcome
        """
        # Record pattern performance
        if interaction.matched_pattern:
            self.pattern_db.record_pattern_use(
                pattern_text=interaction.matched_pattern,
                move_name=interaction.matched_move,
                confidence=interaction.confidence,
                outcome=interaction.outcome,
                interaction=interaction
            )

        # Adjust confidence based on outcome
        if interaction.matched_pattern:
            await self._adjust_confidence(interaction)

        # Check for pattern proposal opportunities
        if interaction.outcome == "success":
            await self._check_for_pattern_proposal(interaction)

        # Check for vocabulary expansion
        if interaction.negotiation_rounds > 0 and interaction.outcome == "success":
            await self._check_for_vocabulary_expansion(interaction)

    async def _adjust_confidence(self, interaction: Interaction):
        """Adjust confidence for pattern based on outcome.

        Success → +0.05 confidence
        Failure → -0.05 confidence

        Args:
            interaction: Interaction with outcome
        """
        min_freq = self.config.learning_min_frequency
        boost = self.config.learning_confidence_boost

        if interaction.outcome == "success":
            adjustment = boost
        elif interaction.outcome == "failure":
            adjustment = -boost
        else:
            return  # No adjustment for negotiations

        self.confidence_adjustments.append(
            ConfidenceAdjustment(
                pattern_text=interaction.matched_pattern,
                move_name=interaction.matched_move,
                adjustment=adjustment,
                reason=f"Pattern {interaction.outcome}",
                timestamp=interaction.timestamp,
                interaction_id=interaction.conversation_id
            )
        )

    async def _check_for_pattern_proposal(self, interaction: Interaction):
        """Check if this interaction suggests a new pattern.

        Triggers:
        - Successful after negotiation
        - User variation not in existing patterns

        Args:
            interaction: Successful interaction
        """
        # Case 1: Successful after negotiation
        if interaction.negotiation_rounds > 0 and interaction.final_understanding:
            await self._propose_from_negotiation(interaction)

        # Case 2: User phrasing not in existing patterns
        if not interaction.matched_pattern or interaction.confidence < 0.6:
            await self._propose_from_variation(interaction)

    async def _propose_from_negotiation(self, interaction: Interaction):
        """Propose pattern learned from successful negotiation.

        When negotiation succeeds, the final understanding is a candidate pattern.

        Args:
            interaction: Interaction after successful negotiation
        """
        # The final understanding after negotiation is the candidate
        candidate = interaction.final_understanding

        if not candidate:
            return

        # Check if we've seen this before
        similar = self.pattern_db.find_similar_patterns(
            candidate,
            threshold=self.config.learning_similarity_threshold
        )

        # If new pattern and successful, propose it
        if not similar:
            proposal = PatternProposal(
                proposal_id=str(uuid.uuid4())[:8],
                pattern_text=candidate,
                move_name=interaction.matched_move,
                source=ProposalSource.NEGOTIATION_SUCCESS,
                source_interactions=[interaction],
                similar_to=None,
                frequency=1,
                success_rate=1.0,  # We know it succeeded
                confidence_boost=0.1,  # Initial estimate
                status=ProposalStatus.PENDING,  # ALWAYS pending (never auto-approve)
                created_at=interaction.timestamp
            )

            self.proposals.append(proposal)

            print(f"[Learning] NEW PROPOSAL: '{candidate}' for move '{interaction.matched_move}'")
            print(f"[Learning] Source: Successful negotiation")
            print(f"[Learning] Status: PENDING (awaits human review)")

    async def _propose_from_variation(self, interaction: Interaction):
        """Propose pattern from user variation.

        When user input differs from existing patterns but leads to success.

        Args:
            interaction: Successful interaction with user variation
        """
        candidate = interaction.user_input

        # Find what it's similar to
        similar = self.pattern_db.find_similar_patterns(
            candidate,
            threshold=self.config.learning_similarity_threshold
        )

        similar_to = similar[0]["pattern_text"] if similar else None

        # Check frequency - only propose if seen multiple times
        # (In production, query database for frequency)
        # For now, create proposal on first success

        proposal = PatternProposal(
            proposal_id=str(uuid.uuid4())[:8],
            pattern_text=candidate,
            move_name=interaction.matched_move,
            source=ProposalSource.USER_VARIATION,
            source_interactions=[interaction],
            similar_to=similar_to,
            frequency=1,
            success_rate=1.0,
            confidence_boost=0.05,
            status=ProposalStatus.PENDING,
            created_at=interaction.timestamp
        )

        self.proposals.append(proposal)

        print(f"[Learning] NEW PROPOSAL: User variation '{candidate}'")
        if similar_to:
            print(f"[Learning] Similar to: '{similar_to}'")

    async def _check_for_vocabulary_expansion(self, interaction: Interaction):
        """Check if negotiation revealed new vocabulary.

        Uses LLM to analyze negotiation and detect synonym relationships.

        Args:
            interaction: Interaction with negotiation
        """
        if not self.llm:
            return  # Need LLM for analysis

        # Use LLM to analyze the negotiation
        prompt = f"""Analyze this negotiation to find vocabulary relationships.

Initial input: {interaction.user_input}
Pattern matched: {interaction.matched_pattern}
Negotiation rounds: {interaction.negotiation_rounds}
Final understanding: {interaction.final_understanding}

Did the user use a synonym or related term for a concept in the pattern?
If yes, what is the canonical term and what synonym did they use?

Return JSON:
{{
  "found_synonym": true/false,
  "canonical_term": "...",
  "synonym": "...",
  "confidence": 0.0-1.0
}}"""

        try:
            response = await self.llm.complete(
                prompt,
                response_schema={
                    "found_synonym": {"type": "boolean"},
                    "canonical_term": {"type": "string"},
                    "synonym": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                max_tokens=100
            )

            if response.content["found_synonym"] and response.content["confidence"] > 0.7:
                vocab_proposal = VocabularyExpansion(
                    canonical_term=response.content["canonical_term"],
                    discovered_synonym=response.content["synonym"],
                    evidence=[interaction],
                    confidence=response.content["confidence"],
                    status=ProposalStatus.PENDING,
                    created_at=interaction.timestamp
                )

                self.vocabulary_proposals.append(vocab_proposal)

                print(f"[Learning] VOCABULARY PROPOSAL: '{vocab_proposal.discovered_synonym}' → '{vocab_proposal.canonical_term}'")

        except Exception as e:
            print(f"[Learning] Vocabulary analysis failed: {e}")

    def get_pending_proposals(self) -> List[PatternProposal]:
        """Get proposals awaiting review.

        Returns:
            List of proposals with status=PENDING
        """
        return [p for p in self.proposals if p.status == ProposalStatus.PENDING]

    def get_pending_vocabulary(self) -> List[VocabularyExpansion]:
        """Get vocabulary proposals awaiting review.

        Returns:
            List of vocabulary expansions with status=PENDING
        """
        return [v for v in self.vocabulary_proposals if v.status == ProposalStatus.PENDING]

    def get_proposal(self, proposal_id: str) -> Optional[PatternProposal]:
        """Get proposal by ID.

        Args:
            proposal_id: Proposal identifier

        Returns:
            PatternProposal or None if not found
        """
        for p in self.proposals:
            if p.proposal_id == proposal_id:
                return p
        return None

    async def enrich_proposal(self, proposal: PatternProposal) -> Dict[str, Any]:
        """Enrich proposal with analysis for human review.

        Args:
            proposal: Pattern proposal

        Returns:
            Dict with proposal, similar patterns, impact analysis, recommendation
        """
        # Find similar patterns for comparison
        similar = self.pattern_db.find_similar_patterns(
            proposal.pattern_text,
            threshold=self.config.learning_similarity_threshold
        )

        # Estimate impact (if LLM available)
        impact_analysis = await self._analyze_impact(proposal) if self.llm else None

        # Generate recommendation
        recommendation = await self._get_recommendation(proposal) if self.llm else "Review manually"

        return {
            "proposal": proposal,
            "similar_patterns": similar,
            "impact_analysis": impact_analysis,
            "recommendation": recommendation
        }

    async def _analyze_impact(self, proposal: PatternProposal) -> Dict[str, Any]:
        """Analyze potential impact of approving proposal.

        Uses LLM to estimate traffic, overlaps, risk.

        Args:
            proposal: Pattern proposal

        Returns:
            Dict with impact analysis
        """
        prompt = f"""Analyze the potential impact of adding this pattern.

New pattern: "{proposal.pattern_text}"
Target move: {proposal.move_name}
Source: {proposal.source.value}
Similar to: {proposal.similar_to or 'None'}

Estimate:
1. How many users might match this pattern? (percentage)
2. Does it overlap with existing patterns (causing conflicts)?
3. What's the risk level (low/medium/high)?

Return JSON with impact analysis."""

        try:
            response = await self.llm.complete(
                prompt,
                response_schema={
                    "estimated_traffic_pct": {"type": "number"},
                    "overlaps": {"type": "array"},
                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "reasoning": {"type": "string"}
                },
                max_tokens=200
            )

            return response.content

        except Exception as e:
            return {"error": str(e)}

    async def _get_recommendation(self, proposal: PatternProposal) -> str:
        """Get LLM recommendation on proposal.

        Args:
            proposal: Pattern proposal

        Returns:
            Recommendation string (APPROVE, MODIFY, REJECT + reasoning)
        """
        prompt = f"""Should this pattern be approved?

Pattern: "{proposal.pattern_text}"
Move: {proposal.move_name}
Source: {proposal.source.value}
Frequency: {proposal.frequency}
Success rate: {proposal.success_rate}
Similar to: {proposal.similar_to or 'None'}

Consider:
1. Does it add value vs existing patterns?
2. Is it safe (won't cause false matches)?
3. Is the language appropriate?

Recommend: APPROVE, MODIFY, or REJECT
Reasoning: Brief explanation"""

        try:
            response = await self.llm.complete(
                prompt,
                response_schema={
                    "recommendation": {"type": "string", "enum": ["APPROVE", "MODIFY", "REJECT"]},
                    "reasoning": {"type": "string"}
                },
                max_tokens=150
            )

            return f"{response.content['recommendation']}: {response.content['reasoning']}"

        except Exception as e:
            return f"Analysis failed: {e}"


# ============================================================================
# Module exports
# ============================================================================

__all__ = [
    "ProposalStatus",
    "ProposalSource",
    "Interaction",
    "PatternProposal",
    "ConfidenceAdjustment",
    "VocabularyExpansion",
    "PatternDatabase",
    "LearningEngine",
]

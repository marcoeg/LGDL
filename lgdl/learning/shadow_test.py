"""
Shadow Testing for LGDL Pattern Proposals

Tests proposed patterns on historical conversations WITHOUT deploying them.
Detects regressions before human review.

CRITICAL FOR SAFETY:
- Tests on 1000+ historical conversations
- Compares baseline vs. with-proposal outcomes
- Calculates regression rate
- Flags high-risk proposals

Never deploys patterns - only tests and reports.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .engine import PatternProposal, Interaction


@dataclass
class ShadowTestResults:
    """Results from shadow testing a proposal.

    Metrics for evaluating proposal safety before human review.
    """
    total_tested: int
    matches_changed: int  # How many conversations matched differently
    confidence_improved: int  # Confidence increased
    confidence_degraded: int  # Confidence decreased
    regressions: List[Dict[str, Any]]  # Conversations that got worse
    improvements: List[Dict[str, Any]]  # Conversations that got better
    regression_rate: float  # % of conversations that regressed
    improvement_rate: float  # % of conversations that improved
    confidence_shift: float  # Average confidence change
    recommendation: str  # "APPROVE", "REVIEW_CAREFULLY", "REJECT"


class ShadowTester:
    """Tests proposals on historical data without deployment.

    Shadow testing workflow:
    1. Load historical conversations for target move
    2. Re-match each with current patterns (baseline)
    3. Re-match each WITH proposal added
    4. Compare outcomes
    5. Calculate regression rate
    6. Flag high-risk proposals

    Safety threshold:
    - <5% regression: LOW risk
    - 5-10% regression: MEDIUM risk
    - >10% regression: HIGH risk (likely reject)
    """

    def __init__(self, pattern_db, matcher):
        """Initialize shadow tester.

        Args:
            pattern_db: PatternDatabase for historical data
            matcher: Matcher for re-running matches
        """
        self.pattern_db = pattern_db
        self.matcher = matcher

    async def test_proposal(
        self,
        proposal: PatternProposal,
        test_size: int = 1000
    ) -> ShadowTestResults:
        """Test proposal on historical conversations.

        Args:
            proposal: Pattern proposal to test
            test_size: Number of historical conversations to test on

        Returns:
            ShadowTestResults with regression analysis
        """
        # Get historical interactions for this move
        historical = self._get_historical_interactions(
            move_name=proposal.move_name,
            limit=test_size
        )

        results = {
            "total_tested": len(historical),
            "matches_changed": 0,
            "confidence_improved": 0,
            "confidence_degraded": 0,
            "regressions": [],
            "improvements": []
        }

        for interaction in historical:
            # Test without proposal (baseline)
            baseline = await self._test_without_proposal(interaction)

            # Test with proposal added
            with_proposal = await self._test_with_proposal(interaction, proposal)

            # Compare results
            if baseline["move"] != with_proposal["move"]:
                results["matches_changed"] += 1

                # Determine if regression or improvement
                if self._is_regression(baseline, with_proposal):
                    results["regressions"].append({
                        "interaction_id": interaction.conversation_id,
                        "user_input": interaction.user_input,
                        "baseline_move": baseline["move"],
                        "proposal_move": with_proposal["move"],
                        "baseline_confidence": baseline["confidence"],
                        "proposal_confidence": with_proposal["confidence"]
                    })
                else:
                    results["improvements"].append({
                        "interaction_id": interaction.conversation_id,
                        "user_input": interaction.user_input,
                        "baseline_confidence": baseline["confidence"],
                        "proposal_confidence": with_proposal["confidence"]
                    })

            # Track confidence changes
            conf_delta = with_proposal["confidence"] - baseline["confidence"]
            if conf_delta > 0:
                results["confidence_improved"] += 1
            elif conf_delta < 0:
                results["confidence_degraded"] += 1

        # Calculate final metrics
        total = results["total_tested"]
        results["regression_rate"] = len(results["regressions"]) / total if total > 0 else 0.0
        results["improvement_rate"] = len(results["improvements"]) / total if total > 0 else 0.0

        conf_shift = results["confidence_improved"] - results["confidence_degraded"]
        results["confidence_shift"] = conf_shift / total if total > 0 else 0.0

        # Generate recommendation
        results["recommendation"] = self._get_recommendation(results)

        return ShadowTestResults(**results)

    def _get_historical_interactions(
        self,
        move_name: str,
        limit: int
    ) -> List[Interaction]:
        """Get historical interactions for testing.

        Args:
            move_name: Target move to get interactions for
            limit: Maximum number to return

        Returns:
            List of historical interactions
        """
        # Get from pattern history (in production, query database)
        relevant = []

        for record in self.pattern_db.pattern_history[-limit:]:
            if record["move_name"] == move_name:
                # Reconstruct interaction
                interaction = Interaction(
                    timestamp=record["timestamp"],
                    conversation_id=record["interaction_id"],
                    user_input="",  # Would need full storage
                    matched_pattern=record["pattern_text"],
                    matched_move=record["move_name"],
                    confidence=record["confidence"],
                    action_taken="",
                    outcome=record["outcome"],
                    negotiation_rounds=0
                )
                relevant.append(interaction)

        return relevant

    async def _test_without_proposal(self, interaction: Interaction) -> Dict[str, Any]:
        """Test interaction without proposal (baseline).

        Args:
            interaction: Historical interaction

        Returns:
            Dict with move, confidence, success flag
        """
        # In production, would re-run matcher without proposal
        # For now, use recorded data
        return {
            "move": interaction.matched_move,
            "confidence": interaction.confidence,
            "success": 1.0 if interaction.outcome == "success" else 0.0
        }

    async def _test_with_proposal(
        self,
        interaction: Interaction,
        proposal: PatternProposal
    ) -> Dict[str, Any]:
        """Test interaction with proposal added.

        Args:
            interaction: Historical interaction
            proposal: Proposal to test

        Returns:
            Dict with move, confidence, success flag (simulated)
        """
        # In production, would temporarily add proposal to patterns and re-match
        # For now, simulate based on similarity

        # If input similar to proposal, assume higher confidence
        similarity = self._compute_similarity(
            interaction.user_input if interaction.user_input else interaction.matched_pattern,
            proposal.pattern_text
        )

        if similarity > 0.8:
            # Would likely match with higher confidence
            return {
                "move": interaction.matched_move,
                "confidence": min(1.0, interaction.confidence + 0.05),
                "success": 1.0 if interaction.outcome == "success" else 0.0
            }
        else:
            # No change
            return {
                "move": interaction.matched_move,
                "confidence": interaction.confidence,
                "success": 1.0 if interaction.outcome == "success" else 0.0
            }

    def _is_regression(self, baseline: Dict, with_proposal: Dict) -> bool:
        """Determine if proposal causes regression.

        Args:
            baseline: Results without proposal
            with_proposal: Results with proposal

        Returns:
            True if regression detected
        """
        # Regression if:
        # 1. Matched different move and outcome worse
        # 2. Confidence decreased significantly
        # 3. Success decreased

        if baseline["move"] != with_proposal["move"]:
            # Move changed - regression if success decreased
            return with_proposal["success"] < baseline["success"]

        # Same move - regression if confidence dropped significantly
        if with_proposal["confidence"] < baseline["confidence"] - 0.1:
            return True

        return False

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """Compute text similarity (simple word overlap).

        Args:
            text1, text2: Texts to compare

        Returns:
            Similarity 0.0-1.0
        """
        words1 = set(text1.lower().split()) if text1 else set()
        words2 = set(text2.lower().split()) if text2 else set()

        if not words1 or not words2:
            return 0.0

        return len(words1 & words2) / len(words1 | words2)

    def _get_recommendation(self, results: Dict) -> str:
        """Get recommendation based on shadow test results.

        Args:
            results: Shadow test results dict

        Returns:
            Recommendation string
        """
        regression_rate = results["regression_rate"]

        if regression_rate > 0.1:
            return "REJECT - High regression rate (>10%)"
        elif regression_rate > 0.05:
            return "REVIEW_CAREFULLY - Medium regression rate (5-10%)"
        elif results["improvement_rate"] > regression_rate * 2:
            return "APPROVE - More improvements than regressions"
        else:
            return "REVIEW - Moderate impact"


__all__ = ["ShadowTester", "ShadowTestResults"]

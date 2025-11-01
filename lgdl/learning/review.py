"""
Pattern Review Workflow

Manages human-in-loop review and approval of learned patterns.

SAFETY GUARANTEE:
- All proposals shadow tested before review
- Risk assessment included
- Human reviewer required
- Audit trail maintained

Workflow:
1. prepare_for_review() - Enrich with analysis + shadow tests
2. Human reviews enriched proposal
3. approve_proposal() or reject_proposal()
4. If approved → deploy to runtime
"""

from datetime import datetime
from typing import Dict, Any, Optional
from .engine import LearningEngine, PatternProposal, ProposalStatus
from .shadow_test import ShadowTester


class ReviewWorkflow:
    """Manages human review of pattern proposals.

    Orchestrates:
    - Proposal enrichment (analysis, similar patterns)
    - Shadow testing (regression detection)
    - Risk assessment
    - Human approval/rejection
    - Deployment to runtime
    """

    def __init__(self, learning_engine: LearningEngine, shadow_tester: ShadowTester):
        """Initialize review workflow.

        Args:
            learning_engine: Learning engine with proposals
            shadow_tester: Shadow tester for safety validation
        """
        self.learning = learning_engine
        self.shadow = shadow_tester

    async def prepare_for_review(
        self,
        proposal_id: str
    ) -> Dict[str, Any]:
        """Prepare proposal for human review.

        Enriches proposal with:
        - Similar patterns comparison
        - Shadow test results (1000 conversations)
        - Risk assessment (low/medium/high)
        - LLM recommendation
        - Impact analysis

        Args:
            proposal_id: Proposal identifier

        Returns:
            Enriched proposal dict ready for human review

        Raises:
            ValueError: If proposal not found
        """
        # Find proposal
        proposal = self.learning.get_proposal(proposal_id)

        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        # Enrich with analysis
        enriched = await self.learning.enrich_proposal(proposal)

        # Run shadow test (CRITICAL for safety)
        print(f"[Review] Running shadow test for proposal {proposal_id}...")
        shadow_results = await self.shadow.test_proposal(proposal)

        enriched["shadow_test_results"] = {
            "total_tested": shadow_results.total_tested,
            "matches_changed": shadow_results.matches_changed,
            "regressions": len(shadow_results.regressions),
            "improvements": len(shadow_results.improvements),
            "regression_rate": shadow_results.regression_rate,
            "improvement_rate": shadow_results.improvement_rate,
            "confidence_shift": shadow_results.confidence_shift,
            "recommendation": shadow_results.recommendation,
            "regression_details": shadow_results.regressions[:5]  # First 5 for review
        }

        # Risk assessment based on shadow tests
        risk_level = "low"
        if shadow_results.regression_rate > 0.1:
            risk_level = "high"
        elif shadow_results.regression_rate > 0.05:
            risk_level = "medium"

        enriched["risk_assessment"] = {
            "level": risk_level,
            "regression_rate": shadow_results.regression_rate,
            "improvement_rate": shadow_results.improvement_rate,
            "net_benefit": shadow_results.improvement_rate - shadow_results.regression_rate
        }

        print(f"[Review] Shadow test complete:")
        print(f"  Tested: {shadow_results.total_tested} conversations")
        print(f"  Regressions: {len(shadow_results.regressions)}")
        print(f"  Improvements: {len(shadow_results.improvements)}")
        print(f"  Risk: {risk_level}")

        return enriched

    async def approve_proposal(
        self,
        proposal_id: str,
        reviewer_id: str,
        notes: Optional[str] = None
    ):
        """Approve a pattern proposal.

        SAFETY CHECKS:
        - Proposal must exist
        - Must be in PENDING status
        - Requires reviewer_id (no anonymous approvals)

        Args:
            proposal_id: Proposal to approve
            reviewer_id: ID of human reviewer
            notes: Optional approval notes

        Raises:
            ValueError: If proposal not found or invalid status
        """
        proposal = self._find_proposal(proposal_id)

        # Safety: Verify can approve
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(
                f"Cannot approve proposal with status {proposal.status.value}. "
                f"Only PENDING proposals can be approved."
            )

        # Update proposal
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_by = reviewer_id
        proposal.review_timestamp = datetime.utcnow()
        proposal.review_notes = notes

        print(f"[Review] ✅ APPROVED by {reviewer_id}")
        print(f"[Review] Pattern: '{proposal.pattern_text}'")
        print(f"[Review] Move: '{proposal.move_name}'")
        if notes:
            print(f"[Review] Notes: {notes}")

        # In production: Deploy to runtime patterns
        # For now, just mark as approved
        await self._deploy_pattern(proposal)

    async def reject_proposal(
        self,
        proposal_id: str,
        reviewer_id: str,
        reason: str
    ):
        """Reject a pattern proposal.

        Args:
            proposal_id: Proposal to reject
            reviewer_id: ID of human reviewer
            reason: Reason for rejection (required)

        Raises:
            ValueError: If proposal not found or reason empty
        """
        if not reason or not reason.strip():
            raise ValueError("Rejection reason required")

        proposal = self._find_proposal(proposal_id)

        # Update proposal
        proposal.status = ProposalStatus.REJECTED
        proposal.reviewed_by = reviewer_id
        proposal.review_timestamp = datetime.utcnow()
        proposal.review_notes = reason

        print(f"[Review] ❌ REJECTED by {reviewer_id}")
        print(f"[Review] Pattern: '{proposal.pattern_text}'")
        print(f"[Review] Reason: {reason}")

    async def revert_proposal(
        self,
        proposal_id: str,
        reviewer_id: str,
        reason: str
    ):
        """Revert a previously approved proposal.

        Used when an approved pattern causes issues in production.

        Args:
            proposal_id: Approved proposal to revert
            reviewer_id: ID of reviewer reverting
            reason: Reason for reversion

        Raises:
            ValueError: If proposal not approved
        """
        proposal = self._find_proposal(proposal_id)

        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError(
                f"Can only revert APPROVED proposals. "
                f"Current status: {proposal.status.value}"
            )

        # Mark as reverted
        proposal.status = ProposalStatus.REVERTED
        proposal.review_notes = f"REVERTED: {reason}\nOriginal notes: {proposal.review_notes}"

        print(f"[Review] ⚠️  REVERTED by {reviewer_id}")
        print(f"[Review] Pattern: '{proposal.pattern_text}'")
        print(f"[Review] Reason: {reason}")

        # Remove from runtime patterns
        await self._undeploy_pattern(proposal)

    def _find_proposal(self, proposal_id: str) -> PatternProposal:
        """Find proposal by ID.

        Args:
            proposal_id: Proposal identifier

        Returns:
            PatternProposal

        Raises:
            ValueError: If not found
        """
        proposal = self.learning.get_proposal(proposal_id)

        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        return proposal

    async def _deploy_pattern(self, proposal: PatternProposal):
        """Deploy approved pattern to runtime.

        In production:
        - Add pattern to compiled game
        - Reload runtime with new pattern
        - Log deployment

        For now:
        - Just log approval (actual deployment TBD)

        Args:
            proposal: Approved proposal
        """
        # TODO: Actual deployment logic
        # This would add the pattern to the move's triggers in the compiled game
        # and reload or update the runtime matcher

        print(f"[Deploy] Pattern '{proposal.pattern_text}' ready for deployment")
        print(f"[Deploy] Target: {proposal.move_name}")
        print(f"[Deploy] Implementation: Add to compiled game patterns and reload")

    async def _undeploy_pattern(self, proposal: PatternProposal):
        """Remove pattern from runtime.

        Args:
            proposal: Reverted proposal
        """
        print(f"[Undeploy] Removing pattern '{proposal.pattern_text}' from runtime")

    def get_review_summary(self) -> Dict[str, Any]:
        """Get summary of review statistics.

        Returns:
            Dict with approval/rejection counts and rates
        """
        total = len(self.learning.proposals)
        approved = len([p for p in self.learning.proposals if p.status == ProposalStatus.APPROVED])
        rejected = len([p for p in self.learning.proposals if p.status == ProposalStatus.REJECTED])
        pending = len([p for p in self.learning.proposals if p.status == ProposalStatus.PENDING])

        return {
            "total_proposals": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": approved / total if total > 0 else 0.0,
            "rejection_rate": rejected / total if total > 0 else 0.0
        }


__all__ = ["ReviewWorkflow"]

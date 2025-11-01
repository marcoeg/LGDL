"""
Learning Engine REST API Endpoints

Provides API for pattern review UI and learning system management.

Endpoints:
- GET /api/learning/proposals - List proposals
- GET /api/learning/proposals/{id} - Get proposal details
- POST /api/learning/proposals/{id}/approve - Approve proposal
- POST /api/learning/proposals/{id}/reject - Reject proposal
- POST /api/learning/proposals/{id}/revert - Revert approved proposal
- GET /api/learning/metrics - Learning system metrics
- GET /api/learning/vocabulary - Vocabulary proposals

SAFETY: All approvals require reviewer_id
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# ============================================================================
# Request/Response Models
# ============================================================================

class ApprovalRequest(BaseModel):
    """Request to approve a pattern proposal."""
    reviewer_id: str = Field(..., description="ID of human reviewer")
    notes: Optional[str] = Field(None, description="Optional approval notes")


class RejectionRequest(BaseModel):
    """Request to reject a pattern proposal."""
    reviewer_id: str = Field(..., description="ID of human reviewer")
    reason: str = Field(..., description="Reason for rejection (required)")


class ReversionRequest(BaseModel):
    """Request to revert an approved proposal."""
    reviewer_id: str = Field(..., description="ID of reviewer reverting")
    reason: str = Field(..., description="Reason for reversion (required)")


class ProposalListResponse(BaseModel):
    """List of proposals."""
    proposals: List[Dict[str, Any]]
    total: int
    status_filter: str


class ProposalDetailResponse(BaseModel):
    """Detailed proposal with enrichment."""
    proposal: Dict[str, Any]
    similar_patterns: List[Dict[str, Any]]
    shadow_test_results: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    impact_analysis: Optional[Dict[str, Any]]
    recommendation: str


class MetricsResponse(BaseModel):
    """Learning system metrics."""
    total_proposals: int
    pending_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    rejection_rate: float
    avg_regression_rate: float


# ============================================================================
# Router
# ============================================================================

router = APIRouter(prefix="/api/learning", tags=["learning"])

# Global instances (injected at startup)
_learning_engine = None
_review_workflow = None


def set_learning_system(learning_engine, review_workflow):
    """Set global learning engine and review workflow.

    Called during app startup.

    Args:
        learning_engine: LearningEngine instance
        review_workflow: ReviewWorkflow instance
    """
    global _learning_engine, _review_workflow
    _learning_engine = learning_engine
    _review_workflow = review_workflow


def get_learning_engine():
    """Dependency: Get learning engine."""
    if _learning_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Learning engine not initialized. Enable with LGDL_ENABLE_LEARNING=true"
        )
    return _learning_engine


def get_review_workflow():
    """Dependency: Get review workflow."""
    if _review_workflow is None:
        raise HTTPException(
            status_code=503,
            detail="Review workflow not initialized"
        )
    return _review_workflow


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/proposals", response_model=ProposalListResponse)
async def list_proposals(
    status: str = "pending",
    learning_engine=Depends(get_learning_engine)
):
    """List pattern proposals by status.

    Args:
        status: Filter by status (pending/approved/rejected/all)

    Returns:
        List of proposals with metadata
    """
    from ..learning.engine import ProposalStatus

    # Get proposals by status
    if status == "all":
        proposals = learning_engine.proposals
    else:
        status_enum = ProposalStatus(status)
        proposals = [p for p in learning_engine.proposals if p.status == status_enum]

    # Convert to dict for JSON
    proposals_dict = []
    for p in proposals:
        proposals_dict.append({
            "proposal_id": p.proposal_id,
            "pattern_text": p.pattern_text,
            "move_name": p.move_name,
            "source": p.source.value,
            "frequency": p.frequency,
            "success_rate": p.success_rate,
            "status": p.status.value,
            "created_at": p.created_at.isoformat(),
            "reviewed_by": p.reviewed_by,
            "similar_to": p.similar_to
        })

    return ProposalListResponse(
        proposals=proposals_dict,
        total=len(proposals_dict),
        status_filter=status
    )


@router.get("/proposals/{proposal_id}", response_model=ProposalDetailResponse)
async def get_proposal_detail(
    proposal_id: str,
    review_workflow=Depends(get_review_workflow)
):
    """Get detailed proposal with shadow test results.

    Includes:
    - Proposal metadata
    - Similar patterns
    - Shadow test results (regression analysis)
    - Risk assessment
    - LLM recommendation

    Args:
        proposal_id: Proposal identifier

    Returns:
        Enriched proposal ready for human review
    """
    try:
        enriched = await review_workflow.prepare_for_review(proposal_id)
        return ProposalDetailResponse(**enriched)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    request: ApprovalRequest,
    review_workflow=Depends(get_review_workflow)
):
    """Approve a pattern proposal.

    SAFETY: Requires reviewer_id (no anonymous approvals).

    Args:
        proposal_id: Proposal to approve
        request: Approval request with reviewer info

    Returns:
        Approval confirmation
    """
    try:
        await review_workflow.approve_proposal(
            proposal_id,
            request.reviewer_id,
            request.notes
        )

        return {
            "status": "approved",
            "proposal_id": proposal_id,
            "reviewer_id": request.reviewer_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    request: RejectionRequest,
    review_workflow=Depends(get_review_workflow)
):
    """Reject a pattern proposal.

    Requires reason (audit trail).

    Args:
        proposal_id: Proposal to reject
        request: Rejection request with reason

    Returns:
        Rejection confirmation
    """
    try:
        await review_workflow.reject_proposal(
            proposal_id,
            request.reviewer_id,
            request.reason
        )

        return {
            "status": "rejected",
            "proposal_id": proposal_id,
            "reviewer_id": request.reviewer_id,
            "reason": request.reason,
            "timestamp": datetime.utcnow().isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/proposals/{proposal_id}/revert")
async def revert_proposal(
    proposal_id: str,
    request: ReversionRequest,
    review_workflow=Depends(get_review_workflow)
):
    """Revert an approved proposal.

    Used when approved pattern causes issues in production.

    Args:
        proposal_id: Proposal to revert
        request: Reversion request with reason

    Returns:
        Reversion confirmation
    """
    try:
        await review_workflow.revert_proposal(
            proposal_id,
            request.reviewer_id,
            request.reason
        )

        return {
            "status": "reverted",
            "proposal_id": proposal_id,
            "reviewer_id": request.reviewer_id,
            "reason": request.reason,
            "timestamp": datetime.utcnow().isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    review_workflow=Depends(get_review_workflow)
):
    """Get learning system metrics.

    Returns:
        System-wide learning metrics
    """
    summary = review_workflow.get_review_summary()

    # Calculate average regression rate from shadow tests
    avg_regression = 0.0
    tested_proposals = [
        p for p in review_workflow.learning.proposals
        if p.shadow_test_results
    ]

    if tested_proposals:
        total_regression = sum(
            p.shadow_test_results.get("regression_rate", 0.0)
            for p in tested_proposals
        )
        avg_regression = total_regression / len(tested_proposals)

    return MetricsResponse(
        total_proposals=summary["total_proposals"],
        pending_count=summary["pending"],
        approved_count=summary["approved"],
        rejected_count=summary["rejected"],
        approval_rate=summary["approval_rate"],
        rejection_rate=summary["rejection_rate"],
        avg_regression_rate=avg_regression
    )


@router.get("/vocabulary")
async def list_vocabulary_proposals(
    learning_engine=Depends(get_learning_engine)
):
    """List vocabulary expansion proposals.

    Returns:
        List of discovered synonyms awaiting review
    """
    proposals = learning_engine.get_pending_vocabulary()

    return {
        "vocabulary_proposals": [
            {
                "canonical_term": v.canonical_term,
                "discovered_synonym": v.discovered_synonym,
                "confidence": v.confidence,
                "status": v.status.value,
                "evidence_count": len(v.evidence),
                "created_at": v.created_at.isoformat()
            }
            for v in proposals
        ],
        "total": len(proposals)
    }


# Export router for app integration
__all__ = ["router", "set_learning_system"]

"""FastAPI routes for Lakshya proposal lifecycle and human approval."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from agent.service import (
    approve_proposal,
    create_replan_proposal,
    reject_proposal,
    undo_proposal,
)
from db import list_proposals
from models import ApprovalRequest, ReplanProposal
from planner.exceptions import SchedulingImpossible
from tools.calendar import CalendarClient, CalendarError, UnauthorizedCalendarMutation

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


def get_calendar_client() -> CalendarClient:
    """FastAPI dependency for obtaining CalendarClient instance."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Google Calendar client not initialized",
    )


@router.post(
    "", response_model=ReplanProposal, status_code=status.HTTP_201_CREATED
)
async def create_proposal(
    goal_id: str = Query(..., description="Target study goal ID"),
    calendar_client: CalendarClient = Depends(get_calendar_client),
) -> ReplanProposal:
    """Generate and persist a replan proposal (ZERO Calendar mutations)."""
    try:
        now = datetime.now(timezone.utc)
        proposal = create_replan_proposal(
            goal_id=goal_id,
            calendar_client=calendar_client,
            now=now,
        )
        return proposal
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SchedulingImpossible as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except CalendarError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred",
        )


@router.get("", response_model=list[ReplanProposal])
async def get_all_proposals() -> list[ReplanProposal]:
    """List all persisted replan proposals."""
    return list_proposals()


@router.post("/{proposal_id}/approve", response_model=ReplanProposal)
async def approve_proposal_endpoint(
    proposal_id: str,
    req: ApprovalRequest,
    calendar_client: CalendarClient = Depends(get_calendar_client),
) -> ReplanProposal:
    """Approve a proposal and apply Calendar mutations only after explicit consent."""
    if not req.approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approval request rejected because approved field is false",
        )
    try:
        return approve_proposal(proposal_id, calendar_client)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UnauthorizedCalendarMutation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except CalendarError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred",
        )


@router.post("/{proposal_id}/reject", response_model=ReplanProposal)
async def reject_proposal_endpoint(
    proposal_id: str,
) -> ReplanProposal:
    """Reject a pending proposal without mutating Calendar."""
    try:
        return reject_proposal(proposal_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred",
        )


@router.post("/{proposal_id}/undo", response_model=ReplanProposal)
async def undo_proposal_endpoint(
    proposal_id: str,
    calendar_client: CalendarClient = Depends(get_calendar_client),
) -> ReplanProposal:
    """Safely undo an applied proposal."""
    try:
        return undo_proposal(proposal_id, calendar_client)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UnauthorizedCalendarMutation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except CalendarError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred",
        )

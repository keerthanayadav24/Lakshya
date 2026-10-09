from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agent.loop import propose_replan
from db import (
    atomic_update_proposal_status,
    get_proposal,
    get_tasks,
    save_audit,
    save_proposal,
    update_proposal_status,
)
from models import AuditEntry, ReplanProposal
from planner.policies import SchedulingPolicy
from tools.calendar import CalendarClient, CalendarError, UnauthorizedCalendarMutation


def create_replan_proposal(
    *,
    goal_id: str,
    calendar_client: CalendarClient,
    now: datetime,
    policy: SchedulingPolicy | None = None,
    reason: str = "Missed Lakshya study blocks detected",
    db_path: str | None = None,
) -> ReplanProposal:
    """Orchestrate missed block detection and proposal creation without mutation."""
    if dt := now:
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise ValueError("now must be timezone-aware")

    # Fetch calendar events
    t_min = now - timedelta(days=7)
    t_max = now + timedelta(days=30)
    events = calendar_client.list_events(t_min, t_max)

    # Fetch tasks
    tasks = get_tasks(goal_id, db_path=db_path)
    if not tasks:
        raise ValueError(f"No study tasks found for goal {goal_id}")

    pol = policy or SchedulingPolicy()
    proposal = propose_replan(
        tasks=tasks,
        calendar_events=events,
        now=now,
        policy=pol,
        reason=reason,
    )

    # Check for duplicate event IDs within proposal
    old_ids = [b.id for b in proposal.old_blocks]
    new_ids = [b.id for b in proposal.new_blocks]
    if len(old_ids) != len(set(old_ids)) or len(new_ids) != len(set(new_ids)):
        raise ValueError("Proposal contains duplicate block IDs")

    # Persist proposal and audit log (ZERO Calendar mutations occur)
    save_proposal(proposal, db_path=db_path)
    audit = AuditEntry(
        id=f"audit_{uuid4().hex[:8]}",
        action="proposal_created",
        timestamp=now,
        details={
            "proposal_id": proposal.id,
            "status": proposal.status,
            "old_blocks_count": len(proposal.old_blocks),
            "new_blocks_count": len(proposal.new_blocks),
        },
        reversible=False,
    )
    save_audit(audit, db_path=db_path)
    return proposal


def approve_proposal(
    proposal_id: str,
    calendar_client: CalendarClient,
    db_path: str | None = None,
) -> ReplanProposal:
    """Approve a pending proposal and mutate ONLY Lakshya-owned events."""
    proposal = get_proposal(proposal_id, db_path=db_path)
    if not proposal:
        raise ValueError(f"Proposal {proposal_id} not found")

    if proposal.status != "pending":
        raise ValueError(
            f"Cannot approve proposal {proposal_id} with status '{proposal.status}'"
        )

    # Atomic state transition from 'pending' to 'applying'
    if not atomic_update_proposal_status(
        proposal_id, ["pending"], "applying", db_path=db_path
    ):
        raise ValueError(
            f"Cannot approve proposal {proposal_id}: "
            "proposal is not pending or is being processed"
        )

    # 1. Pre-verification: duplicate event IDs
    old_ids = [b.id for b in proposal.old_blocks]
    new_ids = [b.id for b in proposal.new_blocks]
    if len(old_ids) != len(set(old_ids)) or len(new_ids) != len(set(new_ids)):
        atomic_update_proposal_status(
            proposal_id, ["applying"], "pending", db_path=db_path
        )
        raise ValueError("Proposal contains duplicate event IDs")

    # 2. Pre-verification: Verify every old block is Lakshya-owned if it exists
    for old_b in proposal.old_blocks:
        evt = calendar_client.get_event(old_b.id)
        if evt and not evt.is_lakshya:
            atomic_update_proposal_status(
                proposal_id, ["applying"], "pending", db_path=db_path
            )
            raise UnauthorizedCalendarMutation(
                f"Cannot modify non-Lakshya calendar event {old_b.id}"
            )

    # 3. Pre-verification: Verify no new block ID collides with a normal user event
    for new_b in proposal.new_blocks:
        evt = calendar_client.get_event(new_b.id)
        if evt and not evt.is_lakshya:
            atomic_update_proposal_status(
                proposal_id, ["applying"], "pending", db_path=db_path
            )
            raise UnauthorizedCalendarMutation(
                f"Cannot overwrite non-Lakshya calendar event {new_b.id}"
            )

    # Execution phase with partial failure tracking
    deleted_old_ids: list[str] = []
    created_new_ids: list[str] = []

    try:
        # Delete old Lakshya study blocks
        for old_b in proposal.old_blocks:
            evt = calendar_client.get_event(old_b.id)
            if evt and evt.is_lakshya:
                calendar_client.delete_study_block(old_b.id)
                deleted_old_ids.append(old_b.id)

        # Create new Lakshya study blocks
        for new_b in proposal.new_blocks:
            calendar_client.create_study_block(new_b)
            created_new_ids.append(new_b.id)

    except Exception as e:
        # Record partial failure state accurately
        update_proposal_status(proposal_id, "partially_applied", db_path=db_path)
        audit_fail = AuditEntry(
            id=f"audit_{uuid4().hex[:8]}",
            action="proposal_failed",
            timestamp=datetime.now(timezone.utc),
            details={
                "proposal_id": proposal_id,
                "error": str(e),
                "deleted_old_ids": deleted_old_ids,
                "created_new_ids": created_new_ids,
            },
            reversible=False,
        )
        save_audit(audit_fail, db_path=db_path)
        raise CalendarError(f"Proposal application failed partway: {e}") from e

    # Update status to applied
    try:
        update_proposal_status(proposal_id, "applied", db_path=db_path)
    except Exception as e:
        audit_db_fail = AuditEntry(
            id=f"audit_{uuid4().hex[:8]}",
            action="proposal_db_update_failed",
            timestamp=datetime.now(timezone.utc),
            details={
                "proposal_id": proposal_id,
                "error": str(e),
                "deleted_old_ids": deleted_old_ids,
                "created_new_ids": created_new_ids,
            },
            reversible=False,
        )
        save_audit(audit_db_fail, db_path=db_path)
        raise ValueError(
            f"Calendar mutations succeeded, but database status update failed: {e}"
        ) from e

    audit = AuditEntry(
        id=f"audit_{uuid4().hex[:8]}",
        action="proposal_applied",
        timestamp=datetime.now(timezone.utc),
        details={"proposal_id": proposal_id},
        reversible=True,
    )
    save_audit(audit, db_path=db_path)

    res = get_proposal(proposal_id, db_path=db_path)
    assert res is not None
    return res


def reject_proposal(
    proposal_id: str,
    db_path: str | None = None,
) -> ReplanProposal:
    """Reject a pending proposal without mutating Calendar."""
    proposal = get_proposal(proposal_id, db_path=db_path)
    if not proposal:
        raise ValueError(f"Proposal {proposal_id} not found")

    if proposal.status != "pending":
        raise ValueError(
            f"Cannot reject proposal {proposal_id} with status '{proposal.status}'"
        )

    if not atomic_update_proposal_status(
        proposal_id, ["pending"], "rejected", db_path=db_path
    ):
        raise ValueError(
            f"Cannot reject proposal {proposal_id}: proposal is not pending"
        )

    audit = AuditEntry(
        id=f"audit_{uuid4().hex[:8]}",
        action="proposal_rejected",
        timestamp=datetime.now(timezone.utc),
        details={"proposal_id": proposal_id},
        reversible=False,
    )
    save_audit(audit, db_path=db_path)

    res = get_proposal(proposal_id, db_path=db_path)
    assert res is not None
    return res


def undo_proposal(
    proposal_id: str,
    calendar_client: CalendarClient,
    db_path: str | None = None,
) -> ReplanProposal:
    """Safely undo an applied proposal by reverting Lakshya-owned changes."""
    proposal = get_proposal(proposal_id, db_path=db_path)
    if not proposal:
        raise ValueError(f"Proposal {proposal_id} not found")

    if proposal.status not in ("applied", "partially_applied", "partially_undone"):
        raise ValueError(
            f"Cannot undo proposal {proposal_id} with status '{proposal.status}'"
        )

    if not atomic_update_proposal_status(
        proposal_id,
        ["applied", "partially_applied", "partially_undone"],
        "undoing",
        db_path=db_path,
    ):
        raise ValueError(
            f"Cannot undo proposal {proposal_id}: "
            "proposal state changed or undo in progress"
        )

    deleted_new_ids: list[str] = []
    restored_old_ids: list[str] = []

    try:
        # Revert new blocks created by proposal (only if Lakshya-owned)
        for new_b in proposal.new_blocks:
            evt = calendar_client.get_event(new_b.id)
            if evt:
                if not evt.is_lakshya:
                    raise UnauthorizedCalendarMutation(
                        f"Cannot delete non-Lakshya event {new_b.id} during undo"
                    )
                calendar_client.delete_study_block(new_b.id)
                deleted_new_ids.append(new_b.id)

        # Restore old blocks removed by proposal
        for old_b in proposal.old_blocks:
            calendar_client.create_study_block(old_b)
            restored_old_ids.append(old_b.id)

    except Exception as e:
        update_proposal_status(proposal_id, "partially_undone", db_path=db_path)
        audit_fail = AuditEntry(
            id=f"audit_{uuid4().hex[:8]}",
            action="undo_failed",
            timestamp=datetime.now(timezone.utc),
            details={
                "proposal_id": proposal_id,
                "error": str(e),
                "deleted_new_ids": deleted_new_ids,
                "restored_old_ids": restored_old_ids,
            },
            reversible=False,
        )
        save_audit(audit_fail, db_path=db_path)
        raise CalendarError(f"Undo operation failed partway: {e}") from e

    try:
        update_proposal_status(proposal_id, "undone", db_path=db_path)
    except Exception as e:
        audit_db_fail = AuditEntry(
            id=f"audit_{uuid4().hex[:8]}",
            action="undo_db_update_failed",
            timestamp=datetime.now(timezone.utc),
            details={
                "proposal_id": proposal_id,
                "error": str(e),
                "deleted_new_ids": deleted_new_ids,
                "restored_old_ids": restored_old_ids,
            },
            reversible=False,
        )
        save_audit(audit_db_fail, db_path=db_path)
        raise ValueError(
            f"Undo mutations succeeded, but database status update failed: {e}"
        ) from e

    audit = AuditEntry(
        id=f"audit_{uuid4().hex[:8]}",
        action="proposal_undone",
        timestamp=datetime.now(timezone.utc),
        details={"proposal_id": proposal_id},
        reversible=False,
    )
    save_audit(audit, db_path=db_path)

    res = get_proposal(proposal_id, db_path=db_path)
    assert res is not None
    return res

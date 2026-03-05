from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Order, OrderAssignment, TimeEntry, User, get_db
from app.security import get_current_user

router = APIRouter(tags=["time"])

INSTALLATION_WORK_TYPE = "installation"
ALLOWED_INSTALL_STATUSES = {"priced", "accepted", "in_production", "ready", "installation", "done"}


def _is_installer_or_admin(user: User) -> bool:
    role_codes = {role.code for role in user.roles}
    return "admin" in role_codes or "installer" in role_codes




def _can_access_order(db: Session, user: User, order_id: int) -> bool:
    if "admin" in {role.code for role in user.roles}:
        return True
    assignment = db.scalar(select(OrderAssignment).where(OrderAssignment.order_id == order_id, OrderAssignment.user_id == user.id))
    return assignment is not None

def _order_total_minutes(db: Session, order_id: int) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(TimeEntry.duration_minutes), 0)).where(
            TimeEntry.order_id == order_id,
            TimeEntry.work_type == INSTALLATION_WORK_TYPE,
        )
    )
    return int(total or 0)


@router.post("/api/orders/{order_id}/time/start")
def start_installation_timer(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_installer_or_admin(current_user):
        raise HTTPException(status_code=403)

    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404)

    if not _can_access_order(db, current_user, order_id):
        raise HTTPException(status_code=403)

    if order.status not in ALLOWED_INSTALL_STATUSES:
        return {"ok": False, "error": "order_status_not_allowed"}

    active_timer = db.scalar(
        select(TimeEntry).where(
            TimeEntry.user_id == current_user.id,
            TimeEntry.work_type == INSTALLATION_WORK_TYPE,
            TimeEntry.ended_at.is_(None),
        )
    )
    if active_timer:
        return {"ok": False, "error": "active_timer_exists", "active_order_id": active_timer.order_id}

    entry = TimeEntry(
        order_id=order_id,
        user_id=current_user.id,
        work_type=INSTALLATION_WORK_TYPE,
        started_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"ok": True, "entry_id": entry.id, "started_at": entry.started_at.isoformat()}


@router.post("/api/orders/{order_id}/time/stop")
def stop_installation_timer(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_installer_or_admin(current_user):
        raise HTTPException(status_code=403)

    if not _can_access_order(db, current_user, order_id):
        raise HTTPException(status_code=403)

    entry = db.scalar(
        select(TimeEntry).where(
            TimeEntry.order_id == order_id,
            TimeEntry.user_id == current_user.id,
            TimeEntry.work_type == INSTALLATION_WORK_TYPE,
            TimeEntry.ended_at.is_(None),
        )
    )
    if not entry:
        return {"ok": False, "error": "no_active_timer"}

    ended_at = datetime.utcnow()
    duration_minutes = round((ended_at - entry.started_at).total_seconds() / 60)
    entry.ended_at = ended_at
    entry.duration_minutes = max(duration_minutes, 0)
    db.commit()

    return {
        "ok": True,
        "duration_minutes": entry.duration_minutes,
        "total_minutes_for_order": _order_total_minutes(db, order_id),
    }


@router.get("/api/orders/{order_id}/time/status")
def installation_timer_status(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404)

    if not _can_access_order(db, current_user, order_id):
        raise HTTPException(status_code=403)

    running_entry = db.scalar(
        select(TimeEntry).where(
            TimeEntry.order_id == order_id,
            TimeEntry.user_id == current_user.id,
            TimeEntry.work_type == INSTALLATION_WORK_TYPE,
            TimeEntry.ended_at.is_(None),
        )
    )

    user_total = db.scalar(
        select(func.coalesce(func.sum(TimeEntry.duration_minutes), 0)).where(
            TimeEntry.order_id == order_id,
            TimeEntry.user_id == current_user.id,
            TimeEntry.work_type == INSTALLATION_WORK_TYPE,
        )
    )

    return {
        "running": running_entry is not None,
        "started_at": running_entry.started_at.isoformat() if running_entry else None,
        "user_total_minutes": int(user_total or 0),
        "order_total_minutes": _order_total_minutes(db, order_id),
    }

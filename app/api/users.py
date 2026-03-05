from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Role, User, get_db
from app.security import get_current_user, hash_password

router = APIRouter(tags=["users"])


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


def _require_admin(user: User):
    if "admin" not in {role.code for role in user.roles}:
        raise HTTPException(status_code=403)


@router.get("/users")
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    users = db.scalars(select(User).order_by(User.username)).all()
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "page_title": "Użytkownicy",
            "users": users,
            "roles": roles,
            "current_user": current_user,
        },
    )


@router.post("/users")
def create_user(
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    role_codes: list[str] = Form([]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    exists = db.scalar(select(User).where(User.username == username))
    if exists:
        return RedirectResponse(url="/users?error=exists", status_code=303)

    user = User(username=username.strip(), password_hash=hash_password(password), full_name=full_name.strip() or None)
    db.add(user)
    if role_codes:
        roles = db.scalars(select(Role).where(Role.code.in_(role_codes))).all()
        user.roles = roles
    db.commit()
    return RedirectResponse(url="/users", status_code=303)

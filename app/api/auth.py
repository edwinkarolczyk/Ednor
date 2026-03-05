from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import User, get_db
from app.security import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_current_user,
    verify_password,
)

router = APIRouter(tags=["auth"])


def set_templates(templates_obj: Jinja2Templates):
    globals()["templates"] = templates_obj


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "page_title": "Logowanie"})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == username))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "page_title": "Logowanie", "error": "Nieprawidłowe dane logowania."},
            status_code=400,
        )

    token = create_session_token(user.id)
    response = RedirectResponse(url="/my-orders", status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, samesite="lax")
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/me")
def me(request: Request, _: User = Depends(get_current_user)):
    return templates.TemplateResponse("me.html", {"request": request, "page_title": "Profil", "current_user": request.state.current_user})

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import joinedload

from app.api.auth import router as auth_router
from app.api.auth import set_templates as auth_set_templates
from app.api.health import router as health_router
from app.api.orders import router as orders_router
from app.api.orders import set_templates as orders_set_templates
from app.api.pricing import router as pricing_router
from app.api.pricing import set_templates as pricing_set_templates
from app.api.quotes import router as quotes_router
from app.api.quotes import set_templates as quotes_set_templates
from app.api.time import router as time_router
from app.api.users import router as users_router
from app.api.users import set_templates as users_set_templates
from app.db import SessionLocal, User, init_db
from app.security import hash_password, read_session_token

app = FastAPI(title="Ednor WEB Skeleton")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


auth_set_templates(templates)
orders_set_templates(templates)
pricing_set_templates(templates)
quotes_set_templates(templates)
users_set_templates(templates)


@app.middleware("http")
async def add_current_user(request: Request, call_next):
    request.state.current_user = None
    token = request.cookies.get("ednor_session")
    user_id = read_session_token(token)
    if user_id:
        db = SessionLocal()
        try:
            user = db.query(User).options(joinedload(User.roles)).filter(User.id == user_id).first()
            if user:
                roles_vm = [SimpleNamespace(code=role.code, name=role.name) for role in (user.roles or [])]
                request.state.current_user = SimpleNamespace(
                    id=user.id,
                    username=user.username,
                    full_name=user.full_name,
                    roles=roles_vm,
                    is_active=user.is_active,
                )
        finally:
            db.close()
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    init_db(hash_password)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(pricing_router)
app.include_router(quotes_router)
app.include_router(users_router)
app.include_router(time_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "page_title": "Panel główny", "current_user": request.state.current_user},
    )

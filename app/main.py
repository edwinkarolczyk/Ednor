from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.auth import router as auth_router
from app.api.auth import set_templates as auth_set_templates
from app.api.health import router as health_router
from app.api.orders import router as orders_router
from app.api.orders import set_templates as orders_set_templates
from app.api.users import router as users_router
from app.api.users import set_templates as users_set_templates
from app.db import SessionLocal, init_db
from app.security import hash_password, read_session_token

app = FastAPI(title="Ednor WEB Skeleton")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


auth_set_templates(templates)
orders_set_templates(templates)
users_set_templates(templates)


@app.middleware("http")
async def add_current_user(request: Request, call_next):
    request.state.current_user = None
    token = request.cookies.get("ednor_session")
    user_id = read_session_token(token)
    if user_id:
        db = SessionLocal()
        try:
            from app.db import User

            request.state.current_user = db.get(User, user_id)
        finally:
            db.close()
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    init_db(hash_password)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(users_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "page_title": "Panel główny", "current_user": request.state.current_user},
    )

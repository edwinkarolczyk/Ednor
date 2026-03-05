from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_api_router
from app.api.health import router as health_router
from app.api.inventory import router as inventory_api_router
from app.api.orders import router as orders_api_router

app = FastAPI(title="Ednor WEB Skeleton")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(orders_api_router)
app.include_router(inventory_api_router)
app.include_router(calendar_api_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "page_title": "Panel główny"})


@app.get("/orders", response_class=HTMLResponse)
def orders_page(request: Request):
    return templates.TemplateResponse("orders.html", {"request": request, "page_title": "Zlecenia"})


@app.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request):
    return templates.TemplateResponse("inventory.html", {"request": request, "page_title": "Magazyn"})


@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request):
    return templates.TemplateResponse("calendar.html", {"request": request, "page_title": "Kalendarz"})

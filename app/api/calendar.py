from fastapi import APIRouter

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/")
def calendar_placeholder() -> dict[str, str]:
    return {"message": "Calendar placeholder"}

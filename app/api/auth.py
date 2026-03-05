from fastapi import APIRouter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/")
def auth_placeholder() -> dict[str, str]:
    return {"message": "Auth placeholder"}

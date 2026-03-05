from fastapi import APIRouter

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/")
def inventory_placeholder() -> dict[str, str]:
    return {"message": "Inventory placeholder"}

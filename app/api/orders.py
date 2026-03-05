from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.config import UPLOADS_DIR

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("/{order_id}/upload")
async def upload_order_file(order_id: str, file: UploadFile = File(...)) -> dict[str, str]:
    target_dir = UPLOADS_DIR / order_id
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "uploaded_file").name
    target_file = target_dir / safe_name

    with target_file.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    await file.close()
    return {"filename": safe_name}

from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import SECRET_KEY
from app.db import User, get_db

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)
serializer = URLSafeSerializer(SECRET_KEY, salt="ednor-session")
SESSION_COOKIE_NAME = "ednor_session"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def read_session_token(cookie: str | None) -> int | None:
    if not cookie:
        return None
    try:
        payload = serializer.loads(cookie)
    except BadSignature:
        return None
    user_id = payload.get("user_id")
    return user_id if isinstance(user_id, int) else None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = read_session_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = read_session_token(token)
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return None
    return user

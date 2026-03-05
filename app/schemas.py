from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str | None = None


class OrderOut(BaseModel):
    id: int
    order_no: int
    title: str
    status: str

from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "ednor.sqlite3"
DATABASE_URL = f"sqlite:///{Path(DB_PATH)}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    roles: Mapped[list["Role"]] = relationship("Role", secondary="user_roles", back_populates="users")
    assignments: Mapped[list["OrderAssignment"]] = relationship("OrderAssignment", back_populates="user")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    users: Mapped[list[User]] = relationship("User", secondary="user_roles", back_populates="roles")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    assignments: Mapped[list["OrderAssignment"]] = relationship("OrderAssignment", back_populates="order")
    attachments: Mapped[list["Attachment"]] = relationship("Attachment", back_populates="order")


class OrderAssignment(Base):
    __tablename__ = "order_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role_code: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="assignments")
    user: Mapped[User] = relationship("User", back_populates="assignments")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    filepath: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="attachments")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(hash_password_fn):
    Base.metadata.create_all(bind=engine)

    from sqlalchemy import select

    seed_roles = {
        "admin": "Admin",
        "production": "Pracownik produkcji",
        "installer": "Monter",
        "service": "Serwisant",
    }

    db = SessionLocal()
    try:
        existing = {role.code: role for role in db.scalars(select(Role)).all()}
        for code, name in seed_roles.items():
            if code not in existing:
                db.add(Role(code=code, name=name))
        db.commit()

        admin = db.scalar(select(User).where(User.username == "admin"))
        if not admin:
            admin = User(username="admin", password_hash=hash_password_fn("admin123"), full_name="Administrator")
            db.add(admin)
            db.commit()
            db.refresh(admin)

        admin_role = db.scalar(select(Role).where(Role.code == "admin"))
        if admin_role and admin_role not in admin.roles:
            admin.roles.append(admin_role)
            db.commit()
    finally:
        db.close()

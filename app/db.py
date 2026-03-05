from datetime import datetime
from pathlib import Path

import logging

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func, inspect
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
    status: Mapped[str] = mapped_column(String(80), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    assignments: Mapped[list["OrderAssignment"]] = relationship("OrderAssignment", back_populates="order")
    attachments: Mapped[list["Attachment"]] = relationship("Attachment", back_populates="order")
    pricing_quotes: Mapped[list["PricingQuote"]] = relationship("PricingQuote", back_populates="order")


class OrderAssignment(Base):
    __tablename__ = "order_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
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


class PricingQuote(Base):
    __tablename__ = "pricing_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    labor_hours_planned: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    labor_hours_manual: Mapped[float | None] = mapped_column(Float, nullable=True)
    use_manual_labor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    labor_rate_per_h: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    power_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    power_rate_per_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    installation_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    service_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    subtotal_net: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_net: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    warranty_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="pricing_quotes")
    lines: Mapped[list["QuoteLine"]] = relationship("QuoteLine", back_populates="quote", cascade="all, delete-orphan")
    fence_input: Mapped["FenceQuoteInput | None"] = relationship(
        "FenceQuoteInput", back_populates="quote", uselist=False, cascade="all, delete-orphan"
    )


class QuoteLine(Base):
    __tablename__ = "quote_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("pricing_quotes.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)

    quote: Mapped[PricingQuote] = relationship("PricingQuote", back_populates="lines")


class FenceTemplate(Base):
    __tablename__ = "fence_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    fence_inputs: Mapped[list["FenceQuoteInput"]] = relationship("FenceQuoteInput", back_populates="template")


class FenceQuoteInput(Base):
    __tablename__ = "fence_quote_inputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("pricing_quotes.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("fence_templates.id"), nullable=False, index=True)
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    height_m: Mapped[float] = mapped_column(Float, nullable=False)
    span_m: Mapped[float] = mapped_column(Float, nullable=False)
    gates_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wickets_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rounding_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="ceil_0_1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    quote: Mapped[PricingQuote] = relationship("PricingQuote", back_populates="fence_input")
    template: Mapped[FenceTemplate] = relationship("FenceTemplate", back_populates="fence_inputs")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(hash_password_fn):
    logger = logging.getLogger(__name__)
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    expected_tables = {
        "orders",
        "pricing_quotes",
        "quote_lines",
        "fence_templates",
        "fence_quote_inputs",
    }
    missing_tables = expected_tables.difference(set(inspector.get_table_names()))
    if missing_tables:
        logger.error("Brakuje tabel po create_all: %s", ", ".join(sorted(missing_tables)))

    expected_columns = {
        "orders": {"status", "client_name", "address"},
        "pricing_quotes": {"use_manual_labor"},
        "fence_quote_inputs": {"created_at"},
    }
    for table_name, columns in expected_columns.items():
        if table_name not in inspector.get_table_names():
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        missing_columns = columns.difference(existing)
        if missing_columns:
            logger.error(
                "Tabela '%s' nie zawiera wymaganych kolumn (%s). Bez Alembic nie wykonujemy ALTER TABLE.",
                table_name,
                ", ".join(sorted(missing_columns)),
            )

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

        basic_template = db.scalar(select(FenceTemplate).where(FenceTemplate.code == "BASIC"))
        if not basic_template:
            db.add(FenceTemplate(code="BASIC", name="Ogrodzenie podstawowe (2 profile poziome)", is_active=True))
            db.commit()
    finally:
        db.close()

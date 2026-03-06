from datetime import datetime
from pathlib import Path

import logging

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

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
    time_entries: Mapped[list["TimeEntry"]] = relationship("TimeEntry", back_populates="user")


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
    source_quote_id: Mapped[int | None] = mapped_column(ForeignKey("quotes.id"), nullable=True, index=True)
    accepted_quote_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("quote_versions.id"), nullable=True, index=True
    )
    deposit_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    materials_check_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    assignments: Mapped[list["OrderAssignment"]] = relationship("OrderAssignment", back_populates="order")
    attachments: Mapped[list["Attachment"]] = relationship("Attachment", back_populates="order")
    pricing_quotes: Mapped[list["PricingQuote"]] = relationship("PricingQuote", back_populates="order")
    time_entries: Mapped[list["TimeEntry"]] = relationship("TimeEntry", back_populates="order")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    order_materials: Mapped[list["OrderMaterial"]] = relationship(
        "OrderMaterial", back_populates="order", cascade="all, delete-orphan"
    )
    reservations: Mapped[list["Reservation"]] = relationship(
        "Reservation", back_populates="order", cascade="all, delete-orphan"
    )
    source_quote: Mapped["Quote | None"] = relationship("Quote", back_populates="orders", foreign_keys=[source_quote_id])


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    work_type: Mapped[str] = mapped_column(String(50), nullable=False, default="installation", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[Order] = relationship("Order", back_populates="time_entries")
    user: Mapped[User] = relationship("User", back_populates="time_entries")


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
    quote_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_quotes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    quote_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    line_type: Mapped[str] = mapped_column(String(50), nullable=False, default="custom")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)

    quote: Mapped[PricingQuote] = relationship("PricingQuote", back_populates="lines")
    quote_version: Mapped["QuoteVersion | None"] = relationship("QuoteVersion", back_populates="lines")


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quote_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    site_address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    versions: Mapped[list["QuoteVersion"]] = relationship(
        "QuoteVersion",
        back_populates="quote",
        cascade="all, delete-orphan",
        foreign_keys="QuoteVersion.quote_id",
    )
    acceptance: Mapped["QuoteAcceptance | None"] = relationship(
        "QuoteAcceptance", back_populates="quote", uselist=False, cascade="all, delete-orphan"
    )
    orders: Mapped[list[Order]] = relationship("Order", back_populates="source_quote", foreign_keys=[Order.source_quote_id])


class QuoteVersion(Base):
    __tablename__ = "quote_versions"
    __table_args__ = (UniqueConstraint("quote_id", "version_no", name="uq_quote_versions_quote_id_version_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    margin_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    warranty_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    quote: Mapped[Quote] = relationship("Quote", back_populates="versions", foreign_keys=[quote_id])
    lines: Mapped[list[QuoteLine]] = relationship("QuoteLine", back_populates="quote_version", cascade="all, delete-orphan")


class QuoteAcceptance(Base):
    __tablename__ = "quote_acceptance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    accepted_version_id: Mapped[int] = mapped_column(ForeignKey("quote_versions.id"), nullable=False, index=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    accepted_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    quote: Mapped[Quote] = relationship("Quote", back_populates="acceptance")
    accepted_version: Mapped[QuoteVersion] = relationship("QuoteVersion")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    payment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="payments")


INVENTORY_CATEGORIES = ["profile", "rury", "blacha", "drut", "elektrody", "inne"]


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    diameter_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    finish: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weight_per_meter_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_per_piece_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    trade_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    purchase_pricing_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    prices: Mapped[list["MaterialPrice"]] = relationship(
        "MaterialPrice", back_populates="material", cascade="all, delete-orphan"
    )
    stock_row: Mapped["Stock | None"] = relationship(
        "Stock", back_populates="material", uselist=False, cascade="all, delete-orphan"
    )
    moves: Mapped[list["StockMove"]] = relationship(
        "StockMove", back_populates="material", cascade="all, delete-orphan"
    )


class MaterialPrice(Base):
    __tablename__ = "material_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    input_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    normalized_price_per_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_price_per_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_price_per_piece: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="PLN")
    valid_from: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    material: Mapped["Material"] = relationship("Material", back_populates="prices")


class Stock(Base):
    __tablename__ = "stock"

    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), primary_key=True)
    qty_on_hand: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    material: Mapped["Material"] = relationship("Material", back_populates="stock_row")


class StockMove(Base):
    __tablename__ = "stock_moves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    move_type: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    material: Mapped["Material"] = relationship("Material", back_populates="moves")


class OrderMaterial(Base):
    __tablename__ = "order_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    qty_required: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    qty_reserved: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="order_materials")
    material: Mapped["Material"] = relationship("Material")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    qty_reserved: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="reserved")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="reservations")
    material: Mapped["Material"] = relationship("Material")


class FenceTemplate(Base):
    __tablename__ = "fence_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))

    fence_inputs: Mapped[list["FenceQuoteInput"]] = relationship("FenceQuoteInput", back_populates="template")
    components: Mapped[list["FenceTemplateComponent"]] = relationship("FenceTemplateComponent", back_populates="template")


class FenceTemplateComponent(Base):
    __tablename__ = "fence_template_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("fence_templates.id"), nullable=False, index=True)
    component_type: Mapped[str] = mapped_column(String(50), nullable=False)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"), nullable=True, index=True)
    formula_type: Mapped[str] = mapped_column(String(50), nullable=False)
    param_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    param_2: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template: Mapped["FenceTemplate"] = relationship("FenceTemplate", back_populates="components")
    material: Mapped["Material | None"] = relationship("Material")


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


def material_stock_state(db: Session, material_id: int) -> tuple[float, float, float]:
    stock_row = db.get(Stock, material_id)
    physical_qty = stock_row.qty_on_hand if stock_row else 0.0
    reserved_qty = db.scalar(
        select(func.coalesce(func.sum(Reservation.qty_reserved), 0.0)).where(
            Reservation.material_id == material_id,
            Reservation.status == "reserved",
        )
    )
    available_qty = physical_qty - float(reserved_qty or 0.0)
    return physical_qty, float(reserved_qty or 0.0), available_qty


def _sqlite_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def _sqlite_add_column(conn, table: str, col: str, coltype: str, default_sql: str | None = None) -> None:
    sql = f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"
    if default_sql is not None:
        sql += f" DEFAULT {default_sql}"
    conn.execute(text(sql))


def _ensure_columns(table: str, cols: list[tuple[str, str, str | None]]) -> None:
    with engine.begin() as conn:
        existing = _sqlite_columns(conn, table)
        for name, coltype, default_sql in cols:
            if name not in existing:
                _sqlite_add_column(conn, table, name, coltype, default_sql)


def init_db(hash_password_fn):
    logger = logging.getLogger(__name__)
    Base.metadata.create_all(bind=engine)

    # SQLite auto-migrations for columns introduced after initial deployment.
    _ensure_columns("quote_versions", [("description", "TEXT", "''")])
    _ensure_columns("pricing_quotes", [("use_manual_labor", "BOOLEAN", "0")])
    _ensure_columns(
        "orders",
        [
            ("deposit_required", "INTEGER", "1"),
            ("materials_check_required", "INTEGER", "1"),
        ],
    )
    _ensure_columns(
        "quote_lines",
        [("line_type", "VARCHAR(50)", "'custom'"), ("quote_version_id", "INTEGER", None)],
    )
    _ensure_columns("fence_quote_inputs", [("created_at", "DATETIME", "CURRENT_TIMESTAMP")])
    _ensure_columns(
        "time_entries",
        [
            ("work_type", "VARCHAR(50)", "'installation'"),
            ("started_at", "DATETIME", None),
            ("ended_at", "DATETIME", None),
            ("duration_minutes", "INTEGER", "0"),
        ],
    )

    _ensure_columns(
        "materials",
        [
            ("width_mm", "REAL", None),
            ("height_mm", "REAL", None),
            ("thickness_mm", "REAL", None),
            ("diameter_mm", "REAL", None),
            ("grade", "TEXT", None),
            ("finish", "TEXT", None),
            ("weight_per_meter_kg", "REAL", None),
            ("weight_per_piece_kg", "REAL", None),
            ("trade_length_m", "REAL", None),
            ("stock_unit", "TEXT", None),
            ("purchase_pricing_mode", "TEXT", None),
        ],
    )
    _ensure_columns(
        "material_prices",
        [
            ("input_price", "REAL", None),
            ("input_unit", "TEXT", None),
            ("normalized_price_per_kg", "REAL", None),
            ("normalized_price_per_mb", "REAL", None),
            ("normalized_price_per_piece", "REAL", None),
        ],
    )

    inspector = inspect(engine)
    expected_tables = {
        "orders",
        "quotes",
        "quote_versions",
        "quote_acceptance",
        "payments",
        "pricing_quotes",
        "quote_lines",
        "materials",
        "material_prices",
        "stock",
        "stock_moves",
        "order_materials",
        "reservations",
        "fence_templates",
        "fence_quote_inputs",
        "fence_template_components",
        "time_entries",
    }
    missing_tables = expected_tables.difference(set(inspector.get_table_names()))
    if missing_tables:
        logger.error("Brakuje tabel po create_all: %s", ", ".join(sorted(missing_tables)))

    expected_columns = {
        "orders": {
            "status",
            "client_name",
            "address",
            "source_quote_id",
            "accepted_quote_version_id",
            "deposit_required",
            "materials_check_required",
        },
        "quote_versions": {"description"},
        "pricing_quotes": {"use_manual_labor"},
        "quote_lines": {"line_type", "quote_version_id"},
        "fence_quote_inputs": {"created_at"},
        "time_entries": {"work_type", "started_at", "ended_at", "duration_minutes"},
    }
    for table_name, columns in expected_columns.items():
        if table_name not in inspector.get_table_names():
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        missing_columns = columns.difference(existing)
        if missing_columns:
            logger.error("Tabela '%s' nie zawiera wymaganych kolumn (%s).", table_name, ", ".join(sorted(missing_columns)))

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

        basic_template = db.scalar(select(FenceTemplate).where(FenceTemplate.code == "BASIC_HORIZONTAL"))
        if not basic_template:
            db.add(FenceTemplate(code="BASIC_HORIZONTAL", name="Ogrodzenie poziome podstawowe", is_active=True))
            db.commit()
    finally:
        db.close()

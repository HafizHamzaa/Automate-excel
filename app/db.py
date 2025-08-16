from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class WageType(str, Enum):
    daily = "daily"
    salary = "salary"


class MessageDirection(str, Enum):
    out = "out"
    in_ = "in"  # stored as 'in' in DB but Python identifier cannot be 'in'


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    assignments: Mapped[list[Assignment]] = relationship("Assignment", back_populates="site")


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    ecommerce_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_e164: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(255), nullable=True)

    wage_type: Mapped[WageType] = mapped_column(SAEnum(WageType), default=WageType.daily, nullable=False)
    daily_rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    base_salary: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    ot_rate_per_hour: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    weekend_rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    assignments: Mapped[list[Assignment]] = relationship("Assignment", back_populates="worker")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    shift: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    worker: Mapped[Worker] = relationship("Worker", back_populates="assignments")
    site: Mapped[Site] = relationship("Site", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("worker_id", "site_id", name="uq_worker_site"),
    )


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    code: Mapped[int] = mapped_column(Integer)
    ot_hours: Mapped[int] = mapped_column(Integer, default=0)
    weekend: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("worker_id", "date", name="uq_worker_date"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wa_message_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    worker_id: Mapped[int | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"), index=True, nullable=True)
    direction: Mapped[str] = mapped_column(String(8))  # 'out' | 'in'
    template: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.utcnow())
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class PayrollRun(Base):
    __tablename__ = "payroll_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    month_yyyymm: Mapped[str] = mapped_column(String(6), index=True)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.utcnow())
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PayrollLine(Base):
    __tablename__ = "payroll_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)

    days_worked: Mapped[int] = mapped_column(Integer, default=0)
    ot_hours: Mapped[int] = mapped_column(Integer, default=0)
    weekend_days: Mapped[int] = mapped_column(Integer, default=0)
    gross: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    deductions: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    net: Mapped[float] = mapped_column(Numeric(14, 2), default=0)


# Engine & session
engine = create_engine(
    settings.db_url,
    echo=False,
    future=True,
)

# Enforce foreign keys in SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:  # pragma: no cover
        pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    os.makedirs("/workspace/logs", exist_ok=True)
    os.makedirs("/workspace/data", exist_ok=True)
    os.makedirs("/workspace/exports/daily", exist_ok=True)
    os.makedirs("/workspace/exports/payroll", exist_ok=True)


@contextlib.contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
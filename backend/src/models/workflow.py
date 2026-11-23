from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.enums import RunStatus
from src.models.base import Base, utc_now


class Batch(Base):
    __tablename__ = 'batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    note: Mapped[str] = mapped_column(String(300), default='')
    created_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Ticket(Base):
    __tablename__ = 'tickets'
    __table_args__ = (UniqueConstraint('batch_id', 'code'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('batches.id'), index=True)
    code: Mapped[str] = mapped_column(String(60))
    segment: Mapped[str] = mapped_column(String(60), index=True)
    procedure: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(12))
    minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    inspected_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    submitted_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AnalysisRun(Base):
    __tablename__ = 'analysis_runs'
    __table_args__ = (UniqueConstraint('batch_id', 'version'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('batches.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    owner: Mapped[str] = mapped_column(String(60))
    parameters: Mapped[dict] = mapped_column(JSON)
    ticket_snapshot: Mapped[list] = mapped_column(JSON)
    sample_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.QUEUED, index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Review(Base):
    __tablename__ = 'reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('analysis_runs.id'), unique=True)
    decision: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Schedule(Base):
    __tablename__ = 'schedules'
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('analysis_runs.id'), index=True)
    recipient: Mapped[str] = mapped_column(String(100))
    interval_minutes: Mapped[int] = mapped_column(Integer)
    next_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Delivery(Base):
    __tablename__ = 'deliveries'
    __table_args__ = (UniqueConstraint('schedule_id', 'scheduled_at'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey('schedules.id'))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    filename: Mapped[str] = mapped_column(String(120))
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

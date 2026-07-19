from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from greenflex.db import Base


class ModelRecord(Base):
    __tablename__ = "model_catalog"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    runtime_name: Mapped[str] = mapped_column(String(128), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    tier: Mapped[str] = mapped_column(String(24), index=True)
    parameter_b: Mapped[str] = mapped_column(String(16))
    context_limit: Mapped[int] = mapped_column(Integer)
    recommended_for_json: Mapped[str] = mapped_column(Text)
    input_rate_micro_rmb_per_million: Mapped[int] = mapped_column(Integer)
    output_rate_micro_rmb_per_million: Mapped[int] = mapped_column(Integer)
    estimated_tokens_per_second: Mapped[int] = mapped_column(Integer)
    estimated_energy_micro_wh_per_1k_output: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class QuoteRecord(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("model_catalog.id"))
    execution_mode: Mapped[str] = mapped_column(String(24))
    item_count: Mapped[int] = mapped_column(Integer)
    input_tokens_est: Mapped[int] = mapped_column(Integer)
    output_tokens_est: Mapped[int] = mapped_column(Integer)
    content_json: Mapped[str] = mapped_column(Text)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    base_price_micro_rmb: Mapped[int] = mapped_column(Integer)
    discount_bps: Mapped[int] = mapped_column(Integer)
    discount_micro_rmb: Mapped[int] = mapped_column(Integer)
    vpp_rebate_micro_rmb: Mapped[int] = mapped_column(Integer, default=0)
    total_price_micro_rmb: Mapped[int] = mapped_column(Integer)
    facility_energy_micro_wh_est: Mapped[int] = mapped_column(Integer)
    carbon_micro_g_est: Mapped[int] = mapped_column(Integer)
    renewable_share_bps: Mapped[int] = mapped_column(Integer)
    signal_version: Mapped[str] = mapped_column(String(64))
    pricing_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    model: Mapped[ModelRecord] = relationship()


class OrderRecord(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("quote_id", name="uq_orders_quote_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    model_id: Mapped[str] = mapped_column(ForeignKey("model_catalog.id"))
    execution_mode: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32), index=True)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quoted_price_micro_rmb: Mapped[int] = mapped_column(Integer)
    actual_price_micro_rmb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_gpu_energy_micro_wh: Mapped[int | None] = mapped_column(Integer, nullable=True)
    incremental_gpu_energy_micro_wh: Mapped[int | None] = mapped_column(Integer, nullable=True)
    facility_energy_micro_wh: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_carbon_micro_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_purged: Mapped[bool] = mapped_column(Boolean, default=False)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    quote: Mapped[QuoteRecord] = relationship()
    model: Mapped[ModelRecord] = relationship()
    items: Mapped[list[OrderItemRecord]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItemRecord.position",
    )


class OrderItemRecord(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "client_item_id", name="uq_order_client_item"),
        Index("ix_order_items_order_status", "order_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    client_item_id: Mapped[str] = mapped_column(String(128))
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_us: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    order: Mapped[OrderRecord] = relationship(back_populates="items")


class ExecutionRecord(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    telemetry_source: Mapped[str] = mapped_column(String(64))
    telemetry_provenance: Mapped[str] = mapped_column(String(24))
    idle_power_mw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_power_mw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_power_mw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PassportRecord(Base):
    __tablename__ = "passports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def model_to_seed_values(item: dict[str, Any]) -> dict[str, Any]:
    return item

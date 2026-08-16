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
    recommended_batch_size: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    is_task_classifier: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    official_data_source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # --- Energy data provenance metadata (L1-L3 + insufficient only) ---
    energy_data_provenance: Mapped[str] = mapped_column(
        String(24), default="insufficient_data", server_default="insufficient_data"
    )
    energy_data_source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    energy_confidence_bps: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    reference_gpu_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameter_count_b: Mapped[float | None] = mapped_column(nullable=True)
    quantization_bits: Mapped[int | None] = mapped_column(nullable=True)
    architecture_family: Mapped[str | None] = mapped_column(String(32), nullable=True)


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


class ModelTaskProfileRecord(Base):
    """Statistical profile of a model on a specific task type."""

    __tablename__ = "model_task_profiles"
    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "task_type",
            "complexity_level",
            "profile_version",
            name="uq_profile_model_task_version",
        ),
        Index("ix_profile_model", "model_id"),
        Index("ix_profile_task", "task_type", "complexity_level"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("model_catalog.id"))
    task_type: Mapped[str] = mapped_column(String(32))
    complexity_level: Mapped[str] = mapped_column(String(16))
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_quality_score_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_std_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_output_tokens_per_1k_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_latency_ms_per_1k_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_energy_micro_wh_per_1k_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_rate_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_version: Mapped[str] = mapped_column(String(64))
    provenance: Mapped[str] = mapped_column(String(24), default="simulated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecommendationDecisionRecord(Base):
    """Audit record of each recommendation decision (no prompts stored)."""

    __tablename__ = "recommendation_decisions"
    __table_args__ = (
        Index("ix_recommendation_tenant", "tenant_id"),
        Index("ix_recommendation_created", "created_at"),
        Index("ix_recommendation_request_hash", "request_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    recommended_model_id: Mapped[str] = mapped_column(ForeignKey("model_catalog.id"))
    recommended_tier: Mapped[str] = mapped_column(String(24))
    recommended_mode: Mapped[str] = mapped_column(String(24))
    confidence_bps: Mapped[int] = mapped_column(Integer)
    quality_risk_level: Mapped[str] = mapped_column(String(16))
    estimated_energy_micro_wh: Mapped[int] = mapped_column(Integer)
    estimated_price_micro_rmb: Mapped[int] = mapped_column(Integer)
    estimated_carbon_micro_g: Mapped[int] = mapped_column(Integer)
    estimated_wait_seconds: Mapped[int] = mapped_column(Integer)
    estimated_execution_seconds: Mapped[int] = mapped_column(Integer)
    reason_codes_json: Mapped[str] = mapped_column(Text)
    alternatives_json: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[str] = mapped_column(String(64))
    provenance: Mapped[str] = mapped_column(String(24), default="simulated")
    shadow_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    user_override_model_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_catalog.id"), nullable=True
    )
    override_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def model_to_seed_values(item: dict[str, Any]) -> dict[str, Any]:
    return item


class GpuEnergyProfileRecord(Base):
    """Per-GPU energy efficiency profile with calibration coefficients.

    The efficiency_factor normalizes benchmark data from a reference GPU
    to the user's actual GPU. A factor of 1.0 means same efficiency as
    the reference; <1.0 means more efficient (less energy per token).
    """

    __tablename__ = "gpu_energy_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    gpu_model: Mapped[str] = mapped_column(String(64), unique=True)
    gpu_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tdp_watts: Mapped[int | None] = mapped_column(nullable=True)
    memory_bandwidth_gbps: Mapped[float | None] = mapped_column(nullable=True)
    compute_tflops_fp16: Mapped[float | None] = mapped_column(nullable=True)
    efficiency_factor: Mapped[float] = mapped_column(default=1.0, server_default="1.0")
    calibration_sample_count: Mapped[int] = mapped_column(default=0, server_default="0")
    last_calibrated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    calibration_provenance: Mapped[str] = mapped_column(
        String(24), default="factory_spec", server_default="factory_spec"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelEnergyBenchmarkRecord(Base):
    """External benchmark dataset entries (Watt Counts, JouleBench, TokenPowerBench, etc.).

    These provide L2 (exact model-GPU match) and L3 (cross-GPU normalized)
    energy data for models the user cannot run locally.
    """

    __tablename__ = "model_energy_benchmarks"
    __table_args__ = (
        Index("ix_benchmark_model_family", "model_family", "parameter_count_b"),
        Index("ix_benchmark_gpu", "gpu_model"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_family: Mapped[str] = mapped_column(String(64))
    parameter_count_b: Mapped[float] = mapped_column()
    quantization_bits: Mapped[int | None] = mapped_column(nullable=True)
    gpu_model: Mapped[str] = mapped_column(String(64))
    gpu_architecture: Mapped[str | None] = mapped_column(String(32), nullable=True)
    avg_power_watts: Mapped[float] = mapped_column()
    throughput_tokens_per_second: Mapped[float] = mapped_column()
    energy_joules_per_token: Mapped[float] = mapped_column()
    energy_wh_per_1k_output: Mapped[float] = mapped_column()
    batch_size: Mapped[int | None] = mapped_column(nullable=True)
    serving_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dataset_source: Mapped[str] = mapped_column(String(64))
    dataset_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provenance_tier: Mapped[str] = mapped_column(
        String(24), default="l2_benchmark_match", server_default="l2_benchmark_match"
    )
    confidence_bps: Mapped[int] = mapped_column(default=7000, server_default="7000")
    measurement_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_reference_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CarbonIntensityCacheRecord(Base):
    """Cached real-time grid carbon intensity with TTL.

    Stores data from Electricity Maps / WattTime / DynLCA APIs.
    When cache expires or API fails, system falls back to synthetic signals.
    """

    __tablename__ = "carbon_intensity_cache"
    __table_args__ = (
        UniqueConstraint("region_code", "interval_start", name="uq_carbon_region_interval"),
        Index("ix_carbon_region_time", "region_code", "interval_start"),
        Index("ix_carbon_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    region_code: Mapped[str] = mapped_column(String(16))
    zone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    carbon_g_per_kwh: Mapped[int] = mapped_column()
    renewable_share_bps: Mapped[int | None] = mapped_column(nullable=True)
    power_mix_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_source: Mapped[str] = mapped_column(String(32))
    data_source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provenance: Mapped[str] = mapped_column(
        String(24), default="estimated", server_default="estimated"
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

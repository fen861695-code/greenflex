from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from greenflex.domain import ExecutionMode, ItemStatus, ModelTier, OrderStatus, Provenance


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ModelCatalogItem(ApiModel):
    id: str
    display_name: str
    runtime_name: str
    tier: ModelTier
    parameter_b: str
    context_limit: int
    recommended_for: list[str]
    input_rate_rmb_per_million: str
    output_rate_rmb_per_million: str
    available: bool
    availability_detail: str
    rate_provenance: Provenance = Provenance.SIMULATED


class PreviewRequest(ApiModel):
    model_id: str
    prompt: str = Field(min_length=1, max_length=8_192)
    system_prompt: str | None = Field(default=None, max_length=4_096)
    max_output_tokens: int = Field(default=256, ge=16, le=512)


class PreviewResponse(ApiModel):
    model_id: str
    output: str
    prompt_tokens: int
    output_tokens: int
    latency_ms: str
    gross_gpu_energy_wh: str | None
    incremental_gpu_energy_wh: str | None
    telemetry_provenance: Provenance
    telemetry_source: str


class BatchItemInput(ApiModel):
    client_item_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    prompt: str = Field(min_length=1, max_length=8_192)
    system_prompt: str | None = Field(default=None, max_length=4_096)
    max_output_tokens: int = Field(default=256, ge=16, le=512)


class QuoteRequest(ApiModel):
    items: list[BatchItemInput] = Field(min_length=1, max_length=500)
    model_id: str | None = None
    tier: ModelTier | None = None
    deadline: datetime | None = None

    @field_validator("items")
    @classmethod
    def unique_client_ids(cls, items: list[BatchItemInput]) -> list[BatchItemInput]:
        ids = [item.client_item_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("client_item_id must be unique")
        return items

    @model_validator(mode="after")
    def model_or_tier_not_both(self) -> QuoteRequest:
        if self.model_id is not None and self.tier is not None:
            raise ValueError("model_id and tier cannot both be set")
        return self


class QuoteOption(ApiModel):
    quote_id: str
    model_id: str
    model_name: str
    tier: ModelTier
    execution_mode: ExecutionMode
    item_count: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    scheduled_start: datetime
    scheduled_end: datetime
    deadline: datetime | None
    base_price_rmb: str
    discount_percent: str
    discount_rmb: str
    vpp_rebate_rmb: str
    total_price_rmb: str
    facility_energy_wh_est: str
    carbon_g_est: str
    renewable_share_percent: str
    pricing_version: str
    signal_version: str
    commercial_provenance: Provenance = Provenance.SIMULATED
    environmental_provenance: Provenance = Provenance.SIMULATED
    expires_at: datetime


class QuoteResponse(ApiModel):
    options: list[QuoteOption]


class CreateOrderRequest(ApiModel):
    quote_id: str


class OrderItemView(ApiModel):
    client_item_id: str
    status: ItemStatus
    output: str | None
    prompt_tokens: int | None
    output_tokens: int | None
    duration_ms: str | None
    error_code: str | None


class OrderView(ApiModel):
    id: str
    quote_id: str
    model_id: str
    model_name: str
    execution_mode: ExecutionMode
    status: OrderStatus
    scheduled_start: datetime
    deadline: datetime | None
    quoted_price_rmb: str
    actual_price_rmb: str | None
    item_count: int
    succeeded_count: int
    failed_count: int
    gross_gpu_energy_wh: str | None
    incremental_gpu_energy_wh: str | None
    location_carbon_g: str | None
    content_purged: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    items: list[OrderItemView] | None = None


class PassportView(ApiModel):
    passport_id: str
    order_id: str
    payload_sha256: str
    payload: dict[str, object]
    created_at: datetime


class ApiError(ApiModel):
    code: str
    message: str

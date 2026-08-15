"""Carbon intensity service with database caching and multi-backend fallback.

Priority chain:
  1. Database cache (not expired) → fastest, no API call
  2. Electricity Maps API (if key configured) → global real-time
  3. DynLCA China regional data → China-specific, no API key needed
  4. Synthetic fallback → always available, clearly labeled SIMULATED

All results are cached in carbon_intensity_cache table with TTL (default 15 min).
When a provider fails, the service transparently falls back to the next tier
and records the provenance downgrade.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from greenflex.carbon_providers import (
    DynLCAProvider,
    ElectricityMapsProvider,
    FallbackCarbonProvider,
)
from greenflex.domain import EnergySignal, Provenance
from greenflex.models import CarbonIntensityCacheRecord

logger = logging.getLogger(__name__)


class CarbonIntensityService:
    """Carbon intensity service with caching and graceful degradation."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        electricity_maps_api_key: str | None = None,
        region_code: str = "CN-HN",
        electricity_maps_zone: str = "CN-CS",
        cache_ttl_minutes: int = 15,
        provider_chain: list[str] | None = None,
    ) -> None:
        self._session = session
        self._region = region_code
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)

        # Build provider chain
        self._providers: list[Any] = []
        chain = provider_chain or ["electricity_maps", "dynlca", "fallback"]

        for name in chain:
            if name == "electricity_maps" and electricity_maps_api_key:
                self._providers.append(
                    ElectricityMapsProvider(
                        api_key=electricity_maps_api_key,
                        zone=electricity_maps_zone,
                        cache_ttl_minutes=cache_ttl_minutes,
                    )
                )
            elif name == "dynlca":
                self._providers.append(DynLCAProvider(region_code=region_code))
            elif name == "fallback":
                self._providers.append(FallbackCarbonProvider())

        if not self._providers:
            self._providers.append(FallbackCarbonProvider())

    @property
    def active_provider_name(self) -> str:
        """Name of the first available provider in the chain."""
        for p in self._providers:
            if hasattr(p, "available") and not p.available:
                continue
            return type(p).__name__
        return "FallbackCarbonProvider"

    async def get_current_signal(self) -> EnergySignal:
        """Get current carbon intensity signal (cached or fetched)."""
        now = datetime.now(timezone.utc)
        return await self.get_signal_at(now)

    async def get_signal_at(self, instant: datetime) -> EnergySignal:
        """Get carbon intensity at a specific time, with cache + fallback."""
        # Step 1: Check database cache
        cached = await self._get_cached(instant)
        if cached is not None:
            return self._record_to_signal(cached)

        # Step 2: Try each provider in chain
        last_error: Exception | None = None
        for provider in self._providers:
            if hasattr(provider, "available") and not provider.available:
                continue
            try:
                signal = provider.signal_at(instant)
                await self._cache_signal(signal, provider)
                return signal
            except Exception as exc:
                logger.warning(
                    "Carbon provider %s failed: %s", type(provider).__name__, exc
                )
                last_error = exc
                continue

        # Step 3: All providers failed — use stale cache if available
        stale = await self._get_stale_cache(instant)
        if stale is not None:
            logger.warning("Using stale carbon cache after all providers failed")
            return self._record_to_signal(stale)

        # Step 4: Ultimate fallback (should never reach here if fallback in chain)
        logger.error("All carbon providers failed and no stale cache: %s", last_error)
        fallback = FallbackCarbonProvider()
        return fallback.signal_at(instant)

    async def get_signals_between(
        self, start: datetime, end: datetime
    ) -> Sequence[EnergySignal]:
        """Get signals for a time range."""
        result: list[EnergySignal] = []
        cursor = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
        while cursor <= end:
            result.append(await self.get_signal_at(cursor))
            cursor += timedelta(minutes=15)
        return result

    async def get_provider_status(self) -> dict[str, Any]:
        """Get status of all providers in the chain."""
        status = []
        for p in self._providers:
            status.append(
                {
                    "name": type(p).__name__,
                    "available": getattr(p, "available", True),
                    "version": getattr(p, "version", "unknown"),
                }
            )
        return {
            "active_provider": self.active_provider_name,
            "region": self._region,
            "cache_ttl_minutes": int(self._cache_ttl.total_seconds() // 60),
            "providers": status,
        }

    # ------------------------------------------------------------------
    # Cache operations
    # ------------------------------------------------------------------
    async def _get_cached(self, instant: datetime) -> CarbonIntensityCacheRecord | None:
        """Get non-expired cache entry for the time slot."""
        slot_start = instant.replace(
            minute=(instant.minute // 15) * 15, second=0, microsecond=0
        )
        now = datetime.now(timezone.utc)

        stmt = select(CarbonIntensityCacheRecord).where(
            CarbonIntensityCacheRecord.region_code == self._region,
            CarbonIntensityCacheRecord.interval_start == slot_start,
            CarbonIntensityCacheRecord.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_stale_cache(
        self, instant: datetime
    ) -> CarbonIntensityCacheRecord | None:
        """Get most recent stale cache entry (expired but usable)."""
        slot_start = instant.replace(
            minute=(instant.minute // 15) * 15, second=0, microsecond=0
        )
        stmt = (
            select(CarbonIntensityCacheRecord)
            .where(
                CarbonIntensityCacheRecord.region_code == self._region,
                CarbonIntensityCacheRecord.interval_start <= slot_start,
            )
            .order_by(CarbonIntensityCacheRecord.interval_start.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _cache_signal(self, signal: EnergySignal, provider: Any) -> None:
        """Persist signal to cache table."""
        now = datetime.now(timezone.utc)
        record = CarbonIntensityCacheRecord(
            id=str(uuid.uuid4()),
            region_code=self._region,
            zone=getattr(provider, "_zone", None),
            interval_start=signal.interval_start,
            carbon_g_per_kwh=signal.carbon_g_per_kwh,
            renewable_share_bps=signal.renewable_share_bps,
            power_mix_json=None,
            data_source=type(provider).__name__,
            data_source_version=getattr(provider, "version", None),
            provenance=signal.provenance,
            fetched_at=now,
            expires_at=now + self._cache_ttl,
        )
        self._session.add(record)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            logger.debug("Cache insert conflict (likely duplicate interval), ignoring")

    @staticmethod
    def _record_to_signal(record: CarbonIntensityCacheRecord) -> EnergySignal:
        """Convert cache record to EnergySignal."""
        return EnergySignal(
            interval_start=record.interval_start,
            price_micro_rmb_per_kwh=660_000,  # cached carbon doesn't store price
            carbon_g_per_kwh=record.carbon_g_per_kwh,
            renewable_share_bps=record.renewable_share_bps or 3000,
            source_version=record.data_source_version or record.data_source,
            provenance=Provenance(record.provenance),
        )

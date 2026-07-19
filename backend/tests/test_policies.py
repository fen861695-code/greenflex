from datetime import UTC, datetime, timedelta

import pytest

from greenflex.domain import DomainError, ExecutionMode
from greenflex.policies import LowestImpactSlotPolicy, TieredPricingPolicy
from greenflex.signals import SyntheticEnergySignalProvider


def test_tiered_flexibility_discounts() -> None:
    policy = TieredPricingPolicy()
    assert policy.discount_bps(ExecutionMode.IMMEDIATE, 40_000) == 0
    assert policy.discount_bps(ExecutionMode.FLEXIBLE, 3_599) == 0
    assert policy.discount_bps(ExecutionMode.FLEXIBLE, 3_600) == 500
    assert policy.discount_bps(ExecutionMode.FLEXIBLE, 14_400) == 1_000
    assert policy.discount_bps(ExecutionMode.FLEXIBLE, 28_800) == 1_500


def test_billing_uses_integer_micro_units() -> None:
    policy = TieredPricingPolicy()
    assert (
        policy.settle_micro_rmb(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            input_rate=100_000,
            output_rate=300_000,
            discount_bps=1_500,
        )
        == 340_000
    )


def test_flexible_slot_stays_before_deadline() -> None:
    now = datetime(2026, 7, 19, 8, tzinfo=UTC)
    deadline = now + timedelta(hours=10)
    policy = LowestImpactSlotPolicy(SyntheticEnergySignalProvider())
    slot = policy.choose_slot(
        mode=ExecutionMode.FLEXIBLE,
        now=now,
        runtime_seconds=3_600,
        deadline=deadline,
    )
    assert slot.end <= deadline
    assert slot.signal.source_version == "synthetic-cn-east-v1"


def test_infeasible_deadline_is_rejected() -> None:
    now = datetime(2026, 7, 19, 8, tzinfo=UTC)
    policy = LowestImpactSlotPolicy(SyntheticEnergySignalProvider())
    with pytest.raises(DomainError, match="截止时间"):
        policy.choose_slot(
            mode=ExecutionMode.FLEXIBLE,
            now=now,
            runtime_seconds=7_200,
            deadline=now + timedelta(minutes=30),
        )

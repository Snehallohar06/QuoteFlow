"""Discount rule engine: tier boundaries, bonuses, caps and refusals."""

from decimal import Decimal

import pytest

from app.models.company_settings import DiscountPolicy, DiscountTier
from app.models.enums import CustomerTier
from app.services.discount_engine import (
    DiscountVerdict,
    evaluate_line_discount,
    resolve_ceiling,
)

pytestmark = pytest.mark.engine


@pytest.fixture
def policy() -> DiscountPolicy:
    """The default policy from the brief: 2% / 5% / 10% / 15% by quantity."""
    return DiscountPolicy()


def evaluate(policy, **overrides):
    kwargs = {
        "quantity": 1,
        "requested_percent": "0",
        "unit_price": "1000.00",
        "cost_price": "0.00",
        "customer_tier": CustomerTier.STANDARD.value,
        "policy": policy,
    }
    kwargs.update(overrides)
    return evaluate_line_discount(**kwargs)


# ---------------------------------------------------------------------------
# Tier bands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "quantity,expected_ceiling",
    [
        (1, "2.00"),
        (5, "2.00"),
        (6, "5.00"),  # band boundary
        (20, "5.00"),
        (21, "10.00"),  # band boundary
        (50, "10.00"),
        (51, "15.00"),  # open-ended top band
        (10_000, "15.00"),
    ],
)
def test_quantity_bands_from_the_brief(policy, quantity, expected_ceiling):
    ceiling, _, _, _ = resolve_ceiling(
        quantity=quantity,
        customer_tier=CustomerTier.STANDARD.value,
        policy=policy,
    )
    assert ceiling == Decimal(expected_ceiling)


def test_discount_at_the_ceiling_is_allowed(policy):
    result = evaluate(policy, quantity=6, requested_percent="5")
    assert result.verdict == DiscountVerdict.ALLOWED
    assert result.applied_percent == Decimal("5.00")


def test_a_hair_over_the_ceiling_needs_approval(policy):
    result = evaluate(policy, quantity=6, requested_percent="5.01")
    assert result.verdict == DiscountVerdict.NEEDS_APPROVAL
    assert result.exceeds_limit is True
    # The requested figure is still priced, so the manager sees the actual ask.
    assert result.applied_percent == Decimal("5.01")


def test_zero_discount_is_always_allowed(policy):
    result = evaluate(policy, quantity=3, requested_percent="0")
    assert result.verdict == DiscountVerdict.ALLOWED
    assert result.reasons == []


# ---------------------------------------------------------------------------
# Customer tier bonus
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tier,expected_ceiling",
    [
        (CustomerTier.STANDARD, "5.00"),
        (CustomerTier.SILVER, "6.00"),
        (CustomerTier.GOLD, "7.00"),
        (CustomerTier.PLATINUM, "8.00"),
    ],
)
def test_tier_bonus_raises_the_ceiling(policy, tier, expected_ceiling):
    ceiling, base, bonus, _ = resolve_ceiling(
        quantity=10, customer_tier=tier.value, policy=policy
    )
    assert base == Decimal("5.00")
    assert ceiling == Decimal(expected_ceiling)
    assert ceiling == base + bonus


def test_gold_customer_gets_a_discount_a_standard_customer_would_not(policy):
    standard = evaluate(
        policy,
        quantity=10,
        requested_percent="7",
        customer_tier=CustomerTier.STANDARD.value,
    )
    gold = evaluate(
        policy,
        quantity=10,
        requested_percent="7",
        customer_tier=CustomerTier.GOLD.value,
    )
    assert standard.verdict == DiscountVerdict.NEEDS_APPROVAL
    assert gold.verdict == DiscountVerdict.ALLOWED


def test_unknown_tier_receives_no_bonus(policy):
    ceiling, base, bonus, _ = resolve_ceiling(
        quantity=10, customer_tier="NOT_A_TIER", policy=policy
    )
    assert bonus == Decimal("0.00")
    assert ceiling == base


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------


def test_product_cap_clamps_a_generous_band(policy):
    """A per-product cap below the band ceiling wins."""
    result = evaluate(
        policy, quantity=100, requested_percent="12", product_max_percent=Decimal("6")
    )
    assert result.max_allowed_percent == Decimal("6.00")
    assert result.verdict == DiscountVerdict.NEEDS_APPROVAL


def test_product_cap_above_the_band_does_not_raise_the_ceiling(policy):
    result = evaluate(
        policy, quantity=3, requested_percent="4", product_max_percent=Decimal("50")
    )
    assert result.max_allowed_percent == Decimal("2.00")


def test_absolute_maximum_is_rejected_outright(policy):
    """Beyond the absolute maximum no approval can help, so it is refused."""
    result = evaluate(policy, quantity=1000, requested_percent="45")
    assert result.verdict == DiscountVerdict.REJECTED
    assert "under any approval" in result.reasons[0]


def test_at_the_absolute_maximum_it_is_only_an_approval(policy):
    result = evaluate(policy, quantity=1000, requested_percent="40")
    assert result.verdict == DiscountVerdict.NEEDS_APPROVAL


# ---------------------------------------------------------------------------
# Cost floor
# ---------------------------------------------------------------------------


def test_discount_below_cost_price_is_rejected(policy):
    """Unit 1000, cost 900: a 15% discount prices it at 850."""
    result = evaluate(
        policy, quantity=100, requested_percent="15", cost_price="900.00"
    )
    assert result.verdict == DiscountVerdict.REJECTED
    assert result.cost_floor_breached is True
    assert result.discounted_unit_price == Decimal("850.00")


def test_discount_exactly_at_cost_price_is_permitted(policy):
    result = evaluate(
        policy, quantity=100, requested_percent="10", cost_price="900.00"
    )
    assert result.verdict == DiscountVerdict.ALLOWED
    assert result.discounted_unit_price == Decimal("900.00")
    assert result.cost_floor_breached is False


def test_cost_floor_can_be_switched_off_by_policy(policy):
    policy.enforce_cost_floor = False
    result = evaluate(
        policy, quantity=100, requested_percent="15", cost_price="900.00"
    )
    assert result.verdict == DiscountVerdict.ALLOWED


def test_zero_cost_price_disables_the_floor_check(policy):
    result = evaluate(policy, quantity=100, requested_percent="15", cost_price="0.00")
    assert result.verdict == DiscountVerdict.ALLOWED


# ---------------------------------------------------------------------------
# Manager override
# ---------------------------------------------------------------------------


def test_override_replaces_the_requested_discount(policy):
    result = evaluate(
        policy,
        quantity=10,
        requested_percent="25",
        override_percent=Decimal("8"),
    )
    assert result.applied_percent == Decimal("8.00")
    # 8% is still above the 5% ceiling, so it remains an approved exception.
    assert result.verdict == DiscountVerdict.NEEDS_APPROVAL
    assert "Manager override" in result.reasons[0]


def test_override_within_policy_clears_the_exception(policy):
    result = evaluate(
        policy, quantity=10, requested_percent="25", override_percent=Decimal("4")
    )
    assert result.verdict == DiscountVerdict.ALLOWED
    assert result.applied_percent == Decimal("4.00")


def test_override_beyond_the_absolute_maximum_is_rejected(policy):
    result = evaluate(
        policy, quantity=10, requested_percent="10", override_percent=Decimal("55")
    )
    assert result.verdict == DiscountVerdict.REJECTED


def test_override_of_zero_is_honoured_not_ignored(policy):
    """A falsy override must still be applied - 0% is a real decision."""
    result = evaluate(
        policy, quantity=10, requested_percent="25", override_percent=Decimal("0")
    )
    assert result.applied_percent == Decimal("0.00")
    assert result.verdict == DiscountVerdict.ALLOWED


# ---------------------------------------------------------------------------
# Configurability
# ---------------------------------------------------------------------------


def test_a_reconfigured_tier_table_changes_the_outcome():
    """The engine reads the policy; it hard-codes nothing."""
    policy = DiscountPolicy(
        tiers=[
            DiscountTier(min_quantity=1, max_quantity=None, max_discount_percent="25"),
        ],
        tier_bonus_percent={CustomerTier.STANDARD.value: "0"},
    )
    result = evaluate(policy, quantity=2, requested_percent="20")
    assert result.max_allowed_percent == Decimal("25.00")
    assert result.verdict == DiscountVerdict.ALLOWED


def test_tiers_are_sorted_on_construction():
    policy = DiscountPolicy(
        tiers=[
            DiscountTier(min_quantity=51, max_quantity=None, max_discount_percent="15"),
            DiscountTier(min_quantity=1, max_quantity=50, max_discount_percent="5"),
        ]
    )
    assert [tier.min_quantity for tier in policy.tiers] == [1, 51]


def test_an_empty_tier_table_is_rejected():
    with pytest.raises(ValueError):
        DiscountPolicy(tiers=[])


def test_a_tier_with_an_inverted_band_is_rejected():
    with pytest.raises(ValueError):
        DiscountTier(min_quantity=10, max_quantity=5, max_discount_percent="5")


def test_a_quantity_in_no_band_gets_no_discount():
    """A gapped tier table must not silently grant the nearest band."""
    policy = DiscountPolicy(
        tiers=[DiscountTier(min_quantity=10, max_quantity=20, max_discount_percent="5")]
    )
    ceiling, base, _, label = resolve_ceiling(
        quantity=5, customer_tier=CustomerTier.STANDARD.value, policy=policy
    )
    assert ceiling == Decimal("0.00")
    assert base == Decimal("0.00")
    assert label is None


def test_quantity_must_be_positive(policy):
    with pytest.raises(ValueError):
        evaluate(policy, quantity=0)

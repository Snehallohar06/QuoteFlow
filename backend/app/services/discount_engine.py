"""Discount rule engine.

Decides, for one line, how much discount the policy permits and whether the
requested figure needs a manager. Like the pricing engine this is pure: it takes
the policy object and the line facts, and returns a verdict.

Four deterministic outcomes, in order of precedence:

1. ``requested > absolute_max_discount_percent``  -> ``REJECTED`` (no approval can
   rescue it; the policy forbids that discount outright).
2. discount would price the line below ``cost_price`` -> ``REJECTED``.
3. ``requested > ceiling``                        -> ``NEEDS_APPROVAL``.
4. otherwise                                     -> ``ALLOWED``.

The ceiling is ``quantity band maximum + customer tier bonus``, then clamped by
any per-product override and by the absolute maximum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.models.company_settings import DiscountPolicy
from app.utils.money import HUNDRED, ZERO, money, rate


class DiscountVerdict(StrEnum):
    ALLOWED = "ALLOWED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    REJECTED = "REJECTED"


@dataclass(slots=True)
class DiscountEvaluation:
    """Explainable result of evaluating one line against the discount policy."""

    verdict: DiscountVerdict
    requested_percent: Decimal
    max_allowed_percent: Decimal
    applied_percent: Decimal

    base_tier_percent: Decimal = ZERO
    tier_bonus_percent: Decimal = ZERO
    product_cap_percent: Decimal | None = None
    absolute_max_percent: Decimal = ZERO
    tier_label: str | None = None

    #: Human-readable justification, surfaced in the manager UI and the audit log.
    reasons: list[str] = field(default_factory=list)
    #: Unit price after the applied discount, used for the cost-floor check.
    discounted_unit_price: Decimal = ZERO
    cost_floor_breached: bool = False

    @property
    def exceeds_limit(self) -> bool:
        return self.requested_percent > self.max_allowed_percent

    def as_context(self) -> dict:
        """Compact dict stored on the request as exception context."""
        return {
            "requested_percent": self.requested_percent,
            "max_allowed_percent": self.max_allowed_percent,
            "base_tier_percent": self.base_tier_percent,
            "tier_bonus_percent": self.tier_bonus_percent,
            "product_cap_percent": self.product_cap_percent,
            "absolute_max_percent": self.absolute_max_percent,
            "tier_label": self.tier_label,
            "verdict": self.verdict.value,
        }


def resolve_ceiling(
    *,
    quantity: int,
    customer_tier: str,
    policy: DiscountPolicy,
    product_max_percent: Decimal | None = None,
) -> tuple[Decimal, Decimal, Decimal, str | None]:
    """Return ``(ceiling, base_tier, tier_bonus, tier_label)`` for a quantity.

    Exposed separately so the catalogue API can tell a customer the maximum
    discount available to them before they submit anything.
    """
    band = policy.tier_for(quantity)
    base = rate(band.max_discount_percent) if band else ZERO
    label = (band.label or f"{band.min_quantity}+") if band else None
    bonus = rate(policy.bonus_for(customer_tier))

    ceiling = base + bonus
    if product_max_percent is not None:
        ceiling = min(ceiling, rate(product_max_percent))
    ceiling = min(ceiling, rate(policy.absolute_max_discount_percent))

    return rate(ceiling), base, bonus, label


def evaluate_line_discount(
    *,
    quantity: int,
    requested_percent: Decimal | str | int,
    unit_price: Decimal | str | int,
    cost_price: Decimal | str | int = ZERO,
    customer_tier: str,
    policy: DiscountPolicy,
    product_max_percent: Decimal | None = None,
    override_percent: Decimal | None = None,
) -> DiscountEvaluation:
    """Evaluate one line against the configured discount policy.

    ``override_percent`` is the discount a manager imposed when approving; when
    given it replaces the requested figure and is still clamped by the policy's
    absolute maximum.
    """
    if quantity < 1:
        raise ValueError("quantity must be at least 1")

    requested = rate(requested_percent)
    absolute_max = rate(policy.absolute_max_discount_percent)
    ceiling, base, bonus, label = resolve_ceiling(
        quantity=quantity,
        customer_tier=customer_tier,
        policy=policy,
        product_max_percent=product_max_percent,
    )

    evaluation = DiscountEvaluation(
        verdict=DiscountVerdict.ALLOWED,
        requested_percent=requested,
        max_allowed_percent=ceiling,
        applied_percent=requested,
        base_tier_percent=base,
        tier_bonus_percent=bonus,
        product_cap_percent=(
            rate(product_max_percent) if product_max_percent is not None else None
        ),
        absolute_max_percent=absolute_max,
        tier_label=label,
    )

    if requested < ZERO or requested > HUNDRED:
        evaluation.verdict = DiscountVerdict.REJECTED
        evaluation.reasons.append(
            f"A discount of {requested}% is not a valid percentage."
        )
        return evaluation

    # A manager override supersedes the request but never the absolute ceiling.
    if override_percent is not None:
        override = rate(override_percent)
        if override > absolute_max:
            evaluation.verdict = DiscountVerdict.REJECTED
            evaluation.reasons.append(
                f"An override of {override}% exceeds the policy maximum of "
                f"{absolute_max}%."
            )
            return evaluation
        evaluation.applied_percent = override
        evaluation.reasons.append(
            f"Manager override: {override}% applied in place of the requested "
            f"{requested}%."
        )

    applied = evaluation.applied_percent
    unit = money(unit_price)
    cost = money(cost_price)
    evaluation.discounted_unit_price = money(unit * (HUNDRED - applied) / HUNDRED)

    # Rule 1: beyond what any approval can grant.
    if applied > absolute_max:
        evaluation.verdict = DiscountVerdict.REJECTED
        evaluation.reasons.append(
            f"A discount of {applied}% exceeds the maximum of {absolute_max}% that "
            f"company policy permits under any approval."
        )
        return evaluation

    # Rule 2: never sell below cost.
    if (
        policy.enforce_cost_floor
        and cost > ZERO
        and evaluation.discounted_unit_price < cost
    ):
        evaluation.cost_floor_breached = True
        evaluation.verdict = DiscountVerdict.REJECTED
        evaluation.reasons.append(
            f"A discount of {applied}% prices the unit at "
            f"{evaluation.discounted_unit_price}, below the cost price of {cost}."
        )
        return evaluation

    # Rule 3: within policy only with a manager's sign-off.
    if applied > ceiling:
        evaluation.verdict = DiscountVerdict.NEEDS_APPROVAL
        detail = f"the {label} band allows {base}%" if label else f"the band allows {base}%"
        if bonus > ZERO:
            detail += f" plus a {bonus}% {customer_tier} tier bonus"
        evaluation.reasons.append(
            f"A discount of {applied}% exceeds the {ceiling}% ceiling for "
            f"{quantity} units ({detail}); manager approval is required."
        )
        return evaluation

    # Rule 4: fully within policy.
    evaluation.verdict = DiscountVerdict.ALLOWED
    if applied > ZERO:
        evaluation.reasons.append(
            f"A discount of {applied}% is within the {ceiling}% ceiling for "
            f"{quantity} units."
        )
    return evaluation

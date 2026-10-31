"""The request state machine, and the money/identifier helpers."""

from decimal import Decimal

import pytest
from bson import Decimal128

from app.core.exceptions import ValidationError, WorkflowError
from app.models.common import jsonable, object_id
from app.models.enums import (
    REQUEST_TRANSITIONS,
    TERMINAL_REQUEST_STATUSES,
    RequestStatus,
)
from app.services.workflow_engine import assert_transition
from app.utils.money import decode_decimals, encode_decimals, money, percent_of, rate

pytestmark = pytest.mark.engine


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def test_every_status_has_a_transition_rule():
    """A status missing from the table would be an unreachable dead end."""
    assert set(REQUEST_TRANSITIONS) == set(RequestStatus)


def test_terminal_statuses_allow_nothing_further():
    for status in TERMINAL_REQUEST_STATUSES:
        assert REQUEST_TRANSITIONS[status] == set()


@pytest.mark.parametrize(
    "current,target",
    [
        (RequestStatus.DRAFT, RequestStatus.SUBMITTED),
        (RequestStatus.SUBMITTED, RequestStatus.UNDER_VALIDATION),
        (RequestStatus.UNDER_VALIDATION, RequestStatus.PRICED),
        (RequestStatus.UNDER_VALIDATION, RequestStatus.VALIDATION_FAILED),
        (RequestStatus.PRICED, RequestStatus.PENDING_APPROVAL),
        (RequestStatus.PRICED, RequestStatus.APPROVED),
        (RequestStatus.APPROVED, RequestStatus.COMPLETED),
        (RequestStatus.APPROVED, RequestStatus.ESCALATED),
        (RequestStatus.ESCALATED, RequestStatus.SUBMITTED),
        (RequestStatus.PENDING_APPROVAL, RequestStatus.APPROVED),
        (RequestStatus.PENDING_APPROVAL, RequestStatus.REJECTED),
        (RequestStatus.PENDING_APPROVAL, RequestStatus.MODIFICATION_REQUESTED),
        (RequestStatus.MODIFICATION_REQUESTED, RequestStatus.SUBMITTED),
        (RequestStatus.VALIDATION_FAILED, RequestStatus.SUBMITTED),
    ],
)
def test_legitimate_transitions_are_allowed(current, target):
    assert_transition(current, target)


@pytest.mark.parametrize(
    "current,target",
    [
        # Cannot skip validation and pricing.
        (RequestStatus.DRAFT, RequestStatus.APPROVED),
        (RequestStatus.SUBMITTED, RequestStatus.APPROVED),
        # Cannot revive a closed request.
        (RequestStatus.COMPLETED, RequestStatus.SUBMITTED),
        (RequestStatus.APPROVED, RequestStatus.SUBMITTED),
        (RequestStatus.REJECTED, RequestStatus.APPROVED),
        (RequestStatus.CANCELLED, RequestStatus.SUBMITTED),
        # Cannot go backwards.
        (RequestStatus.PRICED, RequestStatus.DRAFT),
        (RequestStatus.COMPLETED, RequestStatus.CANCELLED),
        # Cannot self-loop.
        (RequestStatus.DRAFT, RequestStatus.DRAFT),
    ],
)
def test_illegal_transitions_are_refused(current, target):
    with pytest.raises(WorkflowError) as error:
        assert_transition(current, target)
    assert error.value.status_code == 409
    assert error.value.details["current_status"] == current


def test_the_refusal_names_what_would_have_been_allowed():
    with pytest.raises(WorkflowError) as error:
        assert_transition(RequestStatus.APPROVED, RequestStatus.SUBMITTED)
    # APPROVED is no longer a dead end: the document must still be issued and
    # verified before the request may be COMPLETED, and the run can still be
    # parked for a human.
    assert error.value.details["allowed"] == ["COMPLETED", "ESCALATED"]

    with pytest.raises(WorkflowError) as error:
        assert_transition(RequestStatus.DRAFT, RequestStatus.APPROVED)
    assert error.value.details["allowed"] == ["CANCELLED", "ESCALATED", "SUBMITTED"]




def test_a_transition_accepts_plain_strings():
    """Statuses read back from MongoDB are strings, not enum members."""
    assert_transition("DRAFT", "SUBMITTED")


def test_every_non_terminal_status_can_reach_a_terminal_one():
    """No status may trap a request forever."""
    reachable = {}

    def walk(status, seen):
        if status in reachable:
            return reachable[status]
        if status in TERMINAL_REQUEST_STATUSES:
            return True
        return any(
            walk(nxt, seen | {status})
            for nxt in REQUEST_TRANSITIONS[status]
            if nxt not in seen
        )

    for status in RequestStatus:
        assert walk(status, frozenset()), f"{status} cannot be closed"


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def test_a_valid_object_id_round_trips():
    assert str(object_id("6710c0a1b2c3d4e5f6a7b8c9")) == "6710c0a1b2c3d4e5f6a7b8c9"


@pytest.mark.parametrize("value", ["", "nope", "12345", None, "zzzzzzzzzzzzzzzzzzzzzzzz"])
def test_a_bad_identifier_raises_a_422_error(value):
    """A malformed id in a URL must be a client error, not a crash."""
    with pytest.raises(ValidationError) as error:
        object_id(value)
    assert error.value.status_code == 422


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------


def test_money_quantises_and_rounds_half_up():
    assert money("1.005") == Decimal("1.01")
    assert money("1.004") == Decimal("1.00")
    assert money(1) == Decimal("1.00")
    assert money(None) == Decimal("0.00")


def test_rate_quantises_to_two_places():
    assert rate("18") == Decimal("18.00")
    assert rate("2.5") == Decimal("2.50")


def test_percent_of_is_exact():
    assert percent_of("10000.00", "18") == Decimal("1800.00")
    assert percent_of("0.00", "18") == Decimal("0.00")
    assert percent_of("33.33", "7.5") == Decimal("2.50")


def test_decimals_survive_a_round_trip_through_bson():
    payload = {
        "total": Decimal("1234.56"),
        "lines": [{"amount": Decimal("0.01")}],
        "label": "unchanged",
        "count": 3,
    }
    encoded = encode_decimals(payload)
    assert isinstance(encoded["total"], Decimal128)
    assert isinstance(encoded["lines"][0]["amount"], Decimal128)
    assert encoded["label"] == "unchanged"
    assert encoded["count"] == 3

    assert decode_decimals(encoded) == payload


def test_jsonable_converts_nested_decimals_to_floats():
    payload = {
        "amount": Decimal("99.99"),
        "nested": {"rate": Decimal("18.00")},
        "rows": [{"value": Decimal("1.50")}],
        "text": "left alone",
    }
    result = jsonable(payload)
    assert result == {
        "amount": 99.99,
        "nested": {"rate": 18.0},
        "rows": [{"value": 1.5}],
        "text": "left alone",
    }
    assert isinstance(result["amount"], float)

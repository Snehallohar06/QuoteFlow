"""Retry classification and execution budgets.

Two jobs, both deliberately small and pure so they can be tested without a
database or a workflow:

1. **Classify a failure.** Only a TRANSIENT failure is worth retrying. A
   PERMANENT failure is a verdict — the input is wrong, or the policy says no —
   and retrying it would burn budget to reach the same answer.

2. **Track the budget.** Attempts, retries and elapsed time are counted against
   the limits in ``company_settings.execution_policy``, so a run cannot loop
   forever and cannot sit forever.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from time import monotonic

from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    ExecutionTimeout,
    NetworkTimeout,
    NotPrimaryError,
    ServerSelectionTimeoutError,
    WriteConcernError,
)

from app.core.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    QuoteFlowError,
    ValidationError,
    WorkflowError,
)
from app.models.company_settings import ExecutionPolicy
from app.models.enums import FailureClass

logger = logging.getLogger(__name__)

#: Infrastructure faults: the operation might well succeed if tried again.
TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    AutoReconnect,
    ConnectionFailure,
    ExecutionTimeout,
    NetworkTimeout,
    NotPrimaryError,
    ServerSelectionTimeoutError,
    WriteConcernError,
    TimeoutError,
    asyncio.TimeoutError,
    ConnectionError,
    OSError,  # covers IOError: a PDF that could not be written to disk
)

#: Verdicts. Retrying cannot change the outcome.
PERMANENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValidationError,
    BusinessRuleError,
    WorkflowError,
    NotFoundError,
    AuthenticationError,
    PermissionDeniedError,
)


class BudgetExceeded(QuoteFlowError):
    """A configured execution budget was reached before the work finished."""

    error_code = "budget_exceeded"
    status_code = 409


def classify(error: BaseException) -> FailureClass:
    """Decide whether ``error`` is worth retrying.

    Order matters: the permanent list is checked first, because a few of our
    domain errors would otherwise be caught by ``OSError`` and friends through
    multiple inheritance in some drivers.
    """
    if isinstance(error, PERMANENT_EXCEPTIONS):
        return FailureClass.PERMANENT
    if isinstance(error, TRANSIENT_EXCEPTIONS):
        return FailureClass.TRANSIENT
    # An error we have not classified is treated as permanent. Retrying an
    # unknown fault risks repeating a side effect; failing fast is safer and
    # surfaces the gap instead of hiding it behind three silent retries.
    return FailureClass.PERMANENT


def is_retryable(error: BaseException) -> bool:
    return classify(error) is FailureClass.TRANSIENT


@dataclass(slots=True)
class RetryRecord:
    """One retried step, kept for the execution trace and the audit log."""

    step: str
    attempt: int
    failure_class: str
    error: str
    waited_ms: int = 0


@dataclass(slots=True)
class ExecutionBudget:
    """Mutable budget for one pipeline run.

    ``attempt_number`` is the request's lifetime attempt count, not this run's,
    so the per-request ceiling survives restarts and resubmissions.
    """

    policy: ExecutionPolicy
    attempt_number: int = 1
    #: Elapsed time already spent on earlier attempts for this request.
    prior_elapsed_ms: int = 0

    started_at: float = field(default_factory=monotonic)
    retries_used: int = 0
    retries: list[RetryRecord] = field(default_factory=list)

    # ---- elapsed time ----------------------------------------------------

    @property
    def elapsed_ms(self) -> int:
        return int((monotonic() - self.started_at) * 1000)

    @property
    def total_elapsed_ms(self) -> int:
        return self.prior_elapsed_ms + self.elapsed_ms

    # ---- limit checks ----------------------------------------------------

    def attempts_exhausted(self) -> bool:
        return self.attempt_number > self.policy.max_attempts_per_request

    def duration_exceeded(self) -> bool:
        return (
            self.elapsed_ms > self.policy.max_execution_ms
            or self.total_elapsed_ms > self.policy.max_total_execution_ms
        )

    def exceeded(self) -> tuple[bool, str | None]:
        """``(True, reason)`` when any budget is spent."""
        if self.attempts_exhausted():
            return True, (
                f"This request has used all "
                f"{self.policy.max_attempts_per_request} processing attempts."
            )
        if self.elapsed_ms > self.policy.max_execution_ms:
            return True, (
                f"This run exceeded the {self.policy.max_execution_ms} ms "
                f"execution limit."
            )
        if self.total_elapsed_ms > self.policy.max_total_execution_ms:
            return True, (
                f"This request exceeded the "
                f"{self.policy.max_total_execution_ms} ms total execution limit."
            )
        return False, None

    def assert_within_budget(self) -> None:
        spent, reason = self.exceeded()
        if spent:
            raise BudgetExceeded(reason or "The execution budget is exhausted.")

    # ---- the retry loop --------------------------------------------------

    async def run_step(self, step: str, operation):
        """Run ``operation`` with retries for transient failures only.

        Returns the operation's value. Re-raises the last error once the retry
        allowance for the step is spent, or immediately for a permanent failure.
        """
        attempt = 0
        while True:
            self.assert_within_budget()
            try:
                return await operation()
            except BudgetExceeded:
                raise
            except BaseException as error:  # noqa: BLE001 - classified below
                failure = classify(error)
                allowance = self.policy.max_retries_per_step

                if failure is FailureClass.PERMANENT:
                    logger.debug("%s failed permanently: %s", step, error)
                    raise

                if attempt >= allowance:
                    logger.warning(
                        "%s exhausted its %d retries: %s", step, allowance, error
                    )
                    raise

                attempt += 1
                self.retries_used += 1
                wait_seconds = self.policy.backoff_for(attempt)
                self.retries.append(
                    RetryRecord(
                        step=step,
                        attempt=attempt,
                        failure_class=failure.value,
                        error=str(error)[:300],
                        waited_ms=int(wait_seconds * 1000),
                    )
                )
                logger.info(
                    "%s failed transiently (attempt %d/%d), retrying in %.0f ms: %s",
                    step,
                    attempt,
                    allowance,
                    wait_seconds * 1000,
                    error,
                )
                if wait_seconds:
                    await asyncio.sleep(wait_seconds)

    def as_dict(self) -> dict:
        """Budget state for the stored execution trace."""
        return {
            "attempt_number": self.attempt_number,
            "max_attempts": self.policy.max_attempts_per_request,
            "retries_used": self.retries_used,
            "max_retries_per_step": self.policy.max_retries_per_step,
            "elapsed_ms": self.elapsed_ms,
            "total_elapsed_ms": self.total_elapsed_ms,
            "max_execution_ms": self.policy.max_execution_ms,
            "max_total_execution_ms": self.policy.max_total_execution_ms,
            "retries": [
                {
                    "step": record.step,
                    "attempt": record.attempt,
                    "failure_class": record.failure_class,
                    "error": record.error,
                    "waited_ms": record.waited_ms,
                }
                for record in self.retries
            ],
        }

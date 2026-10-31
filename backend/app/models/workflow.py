"""`workflow_executions` collection - the audit trail of the rule engine.

Each run of the pipeline persists one document containing a per-step record:
the inputs it saw, the decision it made and how long it took. This is what makes
the automation explainable after the fact rather than a black box.
"""

from datetime import datetime

from pydantic import Field

from app.models.common import DocumentModel, JsonDict, PyObjectId, utc_now
from app.models.enums import (
    EscalationReason,
    StepStatus,
    WorkflowOutcome,
    WorkflowStep,
)

#: Bumped when step semantics change, so historical executions stay
#: interpretable. 2.0.0 added the document-generation and verification steps,
#: the success gate, and the retry/no-op/escalation/budget boundaries.
ENGINE_VERSION = "2.0.0"


class StepExecution(DocumentModel):
    step: WorkflowStep
    status: StepStatus
    message: str | None = None
    #: Transient-failure retries this step consumed.
    retries: int = 0
    #: Structured result of the step - the figures it produced or the rules it hit.
    output: JsonDict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    duration_ms: int = 0


class WorkflowExecution(DocumentModel):
    request_id: PyObjectId
    request_number: str
    triggered_by: PyObjectId | None = None
    trigger: str = "SUBMISSION"
    engine_version: str = ENGINE_VERSION

    outcome: WorkflowOutcome | None = None
    steps: list[StepExecution] = Field(default_factory=list)
    #: Final status written onto the request by this run.
    resulting_status: str | None = None

    # ---- Boundary controls ------------------------------------------------
    #: This request's lifetime attempt number, against the configured maximum.
    attempt_number: int = 1
    #: Transient-failure retries across every step of this run.
    retries_used: int = 0
    #: Budget state and the retry log, for the audit trail.
    budget: JsonDict = Field(default_factory=dict)
    #: Which success-gate conditions were satisfied.
    gate: JsonDict = Field(default_factory=dict)
    #: Set when the run parked the request for a human.
    escalation_reason: EscalationReason | None = None
    escalation_detail: str | None = None

    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=utc_now)

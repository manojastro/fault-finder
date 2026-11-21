"""Pydantic models for the agent's draft, reports and decisions."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ESCALATE_MESSAGE = "Cannot tell, escalate to a senior technician."
OUT_OF_SCOPE_MESSAGE = (
    "Sorry, I can only help investigate equipment faults on the pumps covered by this demo. "
    "Please describe the fault (machine, symptom, any fault code) or ask your supervisor."
)


class Citation(BaseModel):
    source: Literal["manual", "record"]
    ref: str = Field(description="manual: page number as text, e.g. '13'; record: fault record ID, e.g. 'FR-0042'")
    quote: str = Field(min_length=3, description="exact text from the cited page or record that supports the claim")


class Cause(BaseModel):
    rank: int = Field(ge=1, le=3)
    cause: str
    category: str | None = None
    citations: list[Citation] = Field(min_length=1)


class Check(BaseModel):
    check: str
    citations: list[Citation] = Field(min_length=1)


class Draft(BaseModel):
    status: Literal["proposed", "escalate"]
    summary: str
    causes: list[Cause] = Field(default_factory=list, max_length=3)
    checks: list[Check] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    missing_information: list[str] = Field(default_factory=list)
    escalation_message: str | None = None

    @model_validator(mode="after")
    def _escalation_consistent(self):
        if self.status == "escalate" and not self.escalation_message:
            self.escalation_message = ESCALATE_MESSAGE
        return self


class ReportIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    reporter: str | None = None


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "edit"]
    reviewer: str = Field(min_length=1)
    reason: str | None = None
    edited_draft: Draft | None = None

    @model_validator(mode="after")
    def _rules(self):
        if self.decision == "reject" and not (self.reason and self.reason.strip()):
            raise ValueError("a reject decision needs a reason")
        if self.decision == "edit" and self.edited_draft is None:
            raise ValueError("an edit decision needs edited_draft")
        return self


# Report status values (the approval state machine):
#   safety_stop | out_of_scope       -> terminal, no AI answer / no decision
#   awaiting_approval                -> approved | rejected | approved_with_edits
DECISION_TO_STATUS = {"approve": "approved", "reject": "rejected", "edit": "approved_with_edits"}

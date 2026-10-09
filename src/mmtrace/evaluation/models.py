"""Rule evaluability schema models for MMTrace."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EvaluationOutcome(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    NONE = "NONE"


class EvaluationCoverage(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MissingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    count: int = Field(ge=0)
    step_ids: list[str] = Field(default_factory=list)


class RuleEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    coverage: EvaluationCoverage
    outcome: EvaluationOutcome
    applicable_units: int = Field(ge=0)
    evaluable_units: int = Field(ge=0)
    not_evaluable_units: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    missing_evidence: list[MissingEvidence] = Field(default_factory=list)


__all__ = [
    "EvaluationCoverage",
    "EvaluationOutcome",
    "MissingEvidence",
    "RuleEvaluation",
]

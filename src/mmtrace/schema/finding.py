"""Finding and report schema models for MMTrace."""

from __future__ import annotations

from enum import Enum
from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

JsonValue: TypeAlias = Any


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ReportStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    severity: Severity
    step_id: str | None = None
    title: str
    evidence: JsonValue = None
    explanation: str | None = None
    suggestion: str | None = None


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    status: ReportStatus
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    findings: list[Finding] = Field(default_factory=list)

    @classmethod
    def from_findings(cls, trace_id: str, findings: list[Finding]) -> "Report":
        error_count = sum(1 for finding in findings if finding.severity is Severity.ERROR)
        warning_count = sum(1 for finding in findings if finding.severity is Severity.WARNING)
        info_count = sum(1 for finding in findings if finding.severity is Severity.INFO)
        status = ReportStatus.FAIL if error_count else ReportStatus.PASS

        return cls(
            trace_id=trace_id,
            status=status,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            findings=findings,
        )


__all__ = ["Finding", "Report", "ReportStatus", "Severity"]

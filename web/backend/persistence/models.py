"""Response and persistence boundary models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from mmtrace.evaluation import RuleEvaluation
from mmtrace.schema.finding import Report
from mmtrace.schema.trace import Trace


class ArtifactInput(BaseModel):
    observation_id: str | None = None
    kind: str
    source_path: str | None = None
    temp_path: Path
    stored_name: str
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None

    model_config = {"arbitrary_types_allowed": True}


class SnapshotInput(BaseModel):
    analysis_id: str
    adapter: str
    source_path: Path
    source_filename: str
    trace: Trace
    report: Report
    evaluations: list[RuleEvaluation]
    artifacts: list[ArtifactInput] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class RuleHit(BaseModel):
    rule_id: str
    count: int
    severity: str


class AnalysisSummary(BaseModel):
    analysis_id: str
    trace_id: str | None
    adapter: str
    status: str
    task: str | None
    agent: str | None
    model: str | None
    benchmark: str | None
    step_count: int
    error_count: int
    warning_count: int
    finding_count: int
    analyzed_at: str
    mmtrace_version: str
    rule_hits: list[RuleHit]


class AnalysisDetail(BaseModel):
    analysis_id: str
    trace: dict
    report: dict
    evaluations: list[RuleEvaluation] | None
    artifacts: dict[str, dict[str, str]]

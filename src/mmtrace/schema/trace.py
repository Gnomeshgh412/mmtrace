"""Core MMTrace trajectory schema models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

JsonValue: TypeAlias = Any

Coordinate: TypeAlias = StrictInt | StrictFloat


class MMTraceModel(BaseModel):
    """Base model with JSON-friendly datetime serialization."""

    model_config = ConfigDict(extra="forbid")


class Observation(MMTraceModel):
    observation_id: str | None = None
    image_path: str | None = None
    width: Annotated[StrictInt | None, Field(ge=0)] = None
    height: Annotated[StrictInt | None, Field(ge=0)] = None
    viewport_width: Annotated[StrictInt | None, Field(ge=0)] = None
    viewport_height: Annotated[StrictInt | None, Field(ge=0)] = None
    timestamp: datetime | None = None


class ModelInput(MMTraceModel):
    model_call_id: str | None = None
    model: str | None = None
    observation_ids: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None


class Action(MMTraceModel):
    action_id: str | None = None
    type: str | None = None
    x: Coordinate | None = None
    y: Coordinate | None = None
    target: str | None = None
    coordinate_space: str | None = None
    timestamp: datetime | None = None


class ExecutionResult(MMTraceModel):
    status: str | None = None
    error: str | None = None
    timestamp: datetime | None = None


class PostState(MMTraceModel):
    observation: Observation | None = None
    url: str | None = None
    window_title: str | None = None
    state_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    timestamp: datetime | None = None


class Step(MMTraceModel):
    step_id: str | None = None
    observation: Observation | None = None
    model_input: ModelInput | None = None
    action: Action | None = None
    execution: ExecutionResult | None = None
    post_state: PostState | None = None


class Trace(MMTraceModel):
    trace_id: str | None = None
    task: str | None = None
    agent: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)


__all__ = [
    "Action",
    "ExecutionResult",
    "ModelInput",
    "Observation",
    "PostState",
    "Step",
    "Trace",
]

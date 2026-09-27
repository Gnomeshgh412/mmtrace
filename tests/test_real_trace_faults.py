import json
from datetime import datetime, timezone
from pathlib import Path

from mmtrace.adapters.browser_use import BrowserUseAdapter
from mmtrace.checks.coordinate import (
    CoordinateOutOfFrameCheck,
    CoordinateSpaceMismatchCheck,
)
from mmtrace.checks.observation import (
    MissingObservationCheck,
    ObservationNotInModelContextCheck,
    StaleObservationCheck,
)
from mmtrace.checks.verification import MissingPostActionVerificationCheck
from mmtrace.engine import CheckEngine
from mmtrace.schema.finding import ReportStatus, Severity
from mmtrace.schema.trace import ExecutionResult, ModelInput

REAL_HISTORY = Path(__file__).parents[1] / "examples" / "browser_use_real" / "history.json"


def load_real_trace():
    return BrowserUseAdapter().load(REAL_HISTORY)


def source_action_count() -> int:
    data = json.loads(REAL_HISTORY.read_text(encoding="utf-8"))
    history = data.get("history") if isinstance(data, dict) else data
    count = 0
    for item in history:
        model_output = item.get("model_output") if isinstance(item, dict) else None
        actions = model_output.get("action") if isinstance(model_output, dict) else []
        if isinstance(actions, list):
            count += len(actions)
        elif actions:
            count += 1
    return count


def click_step(trace):
    for step in trace.steps:
        if step.action is not None and step.action.type == "click":
            return step
    raise AssertionError("real trace must contain a click step")


def test_real_trace_baseline_passes_and_preserves_action_count() -> None:
    trace = load_real_trace()
    report = CheckEngine().run(trace)

    assert source_action_count() == 4
    assert sum(1 for step in trace.steps if step.action is not None) == 4
    assert report.status is ReportStatus.PASS
    assert report.error_count == 0
    assert report.warning_count == 0


def test_mmtrace001_fault_missing_observation_for_click() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    step.observation = None

    findings = MissingObservationCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE001"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].step_id == step.step_id
    assert findings[0].evidence["has_observation"] is False
    assert findings[0].evidence["action_type"] == "click"


def test_mmtrace002_fault_observation_not_in_model_context() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    assert step.observation is not None
    step.model_input = ModelInput(
        model_call_id="fault-call",
        model="fault-model",
        observation_ids=["different-observation-id"],
    )

    findings = ObservationNotInModelContextCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE002"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].step_id == step.step_id
    assert findings[0].evidence["observation_id"] == step.observation.observation_id
    assert findings[0].evidence["model_observation_ids"] == ["different-observation-id"]


def test_mmtrace002_boundary_observation_in_model_context() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    assert step.observation is not None
    step.model_input = ModelInput(
        model_call_id="ok-call",
        model="fault-model",
        observation_ids=[step.observation.observation_id],
    )

    findings = ObservationNotInModelContextCheck().run(trace)

    assert findings == []


def test_mmtrace003_fault_coordinate_out_of_frame() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    assert step.observation is not None
    assert step.action is not None
    step.observation.viewport_width = 1280
    step.observation.viewport_height = 720
    step.action.coordinate_space = "viewport"
    step.action.x = 1400
    step.action.y = 400

    findings = CoordinateOutOfFrameCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE003"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].step_id == step.step_id
    assert findings[0].evidence["x"] == 1400
    assert findings[0].evidence["y"] == 400
    assert findings[0].evidence["frame_width"] == 1280
    assert findings[0].evidence["frame_height"] == 720


def test_mmtrace003_boundary_coordinate_inside_frame() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    assert step.observation is not None
    assert step.action is not None
    step.observation.viewport_width = 1280
    step.observation.viewport_height = 720
    step.action.coordinate_space = "viewport"
    step.action.x = 500
    step.action.y = 400

    findings = CoordinateOutOfFrameCheck().run(trace)

    assert findings == []


def test_mmtrace004_fault_coordinate_space_mismatch() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    assert step.observation is not None
    assert step.action is not None
    trace.metadata["expected_coordinate_space"] = "viewport"
    step.observation.width = 1280
    step.observation.height = 720
    step.action.coordinate_space = "image"
    step.action.x = 500
    step.action.y = 400

    findings = CoordinateSpaceMismatchCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE004"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].step_id == step.step_id
    assert findings[0].evidence["action_coordinate_space"] == "image"
    assert findings[0].evidence["expected_coordinate_space"] == "viewport"
    assert findings[0].evidence["available_transform"] is None


def test_mmtrace004_boundary_matching_coordinate_space() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    assert step.observation is not None
    assert step.action is not None
    trace.metadata["expected_coordinate_space"] = "viewport"
    step.observation.viewport_width = 1280
    step.observation.viewport_height = 720
    step.action.coordinate_space = "viewport"
    step.action.x = 500
    step.action.y = 400

    findings = CoordinateSpaceMismatchCheck().run(trace)

    assert findings == []


def test_mmtrace004_boundary_transform_suppresses_mismatch() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    assert step.observation is not None
    assert step.action is not None
    trace.metadata["expected_coordinate_space"] = "viewport"
    trace.metadata["coordinate_transform"] = {"scale": 0.5}
    step.observation.width = 1280
    step.observation.height = 720
    step.action.coordinate_space = "image"
    step.action.x = 500
    step.action.y = 400

    findings = CoordinateSpaceMismatchCheck().run(trace)

    assert findings == []


def test_mmtrace005_fault_stale_observation() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    setup_step = trace.steps[0]
    assert step.observation is not None
    assert step.action is not None
    assert setup_step.post_state is not None
    assert setup_step.post_state.observation is not None
    step.observation.observation_id = "obs-a"
    step.observation.timestamp = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
    setup_step.post_state.observation.observation_id = "obs-b"
    setup_step.post_state.observation.timestamp = datetime(
        2026, 9, 27, 10, 0, 5, tzinfo=timezone.utc
    )
    step.action.timestamp = datetime(2026, 9, 27, 10, 0, 10, tzinfo=timezone.utc)

    findings = StaleObservationCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE005"
    assert findings[0].severity is Severity.WARNING
    assert findings[0].step_id == step.step_id
    assert findings[0].evidence["used_observation_id"] == "obs-a"
    assert findings[0].evidence["newer_observation_id"] == "obs-b"


def test_mmtrace005_boundary_time_gap_without_new_observation() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    assert step.observation is not None
    assert step.action is not None
    for other_step in trace.steps:
        if other_step is not step and other_step.observation is not None:
            other_step.observation.timestamp = None
        if other_step.post_state is not None and other_step.post_state.observation is not None:
            other_step.post_state.observation.timestamp = None
    step.observation.observation_id = "obs-a"
    step.observation.timestamp = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
    step.action.timestamp = datetime(2026, 9, 27, 11, 0, 0, tzinfo=timezone.utc)

    findings = StaleObservationCheck().run(trace)

    assert findings == []


def test_mmtrace006_fault_success_without_post_state() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    step.execution = ExecutionResult(status="success")
    step.post_state = None

    findings = MissingPostActionVerificationCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE006"
    assert findings[0].severity is Severity.WARNING
    assert findings[0].step_id == step.step_id
    assert findings[0].evidence["execution_status"] == "success"
    assert findings[0].evidence["has_post_state"] is False


def test_mmtrace006_boundary_success_with_post_state() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    step.execution = ExecutionResult(status="success")
    assert step.post_state is not None

    findings = MissingPostActionVerificationCheck().run(trace)

    assert findings == []


def test_mmtrace006_boundary_failed_without_post_state() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    step.execution = ExecutionResult(status="failed", error="failed click")
    step.post_state = None

    findings = MissingPostActionVerificationCheck().run(trace)

    assert findings == []


def test_full_default_engine_runs_on_faulted_real_trace() -> None:
    trace = load_real_trace().model_copy(deep=True)
    step = click_step(trace)
    step.observation = None

    report = CheckEngine().run(trace)

    assert report.findings
    assert any(finding.rule_id == "MMTRACE001" for finding in report.findings)

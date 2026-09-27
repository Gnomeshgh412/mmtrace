from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from mmtrace.schema.finding import Finding, Report, ReportStatus, Severity
from mmtrace.schema.trace import Trace


def complete_trace_data() -> dict:
    return {
        "trace_id": "trace-001",
        "task": "Open the docs page",
        "agent": "example-agent",
        "start_time": "2026-09-26T10:00:00Z",
        "end_time": "2026-09-26T10:00:05Z",
        "metadata": {
            "browser": "chromium",
            "attempt": 1,
            "flags": ["vision", "computer-use"],
            "nested": {"ok": True, "score": 0.98, "none": None},
        },
        "steps": [
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-001",
                    "image_path": "screenshots/obs-001.png",
                    "width": 1280,
                    "height": 720,
                    "viewport_width": 1280,
                    "viewport_height": 720,
                    "timestamp": "2026-09-26T10:00:01Z",
                },
                "model_input": {
                    "model_call_id": "call-001",
                    "model": "example-model",
                    "observation_ids": ["obs-001"],
                    "timestamp": "2026-09-26T10:00:02Z",
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "x": 42,
                    "y": 84.5,
                    "target": "Docs",
                    "coordinate_space": "viewport",
                    "timestamp": "2026-09-26T10:00:03Z",
                },
                "execution": {
                    "status": "success",
                    "error": None,
                    "timestamp": "2026-09-26T10:00:04Z",
                },
                "post_state": {
                    "observation": {
                        "observation_id": "obs-002",
                        "image_path": "screenshots/obs-002.png",
                        "width": 1280,
                        "height": 720,
                    },
                    "url": "https://example.com/docs",
                    "window_title": "Docs",
                    "state_metadata": {"loaded": True, "timing_ms": 250},
                    "timestamp": "2026-09-26T10:00:05Z",
                },
            }
        ],
    }


def test_complete_trace_parses() -> None:
    trace = Trace.model_validate(complete_trace_data())

    assert trace.trace_id == "trace-001"
    assert trace.steps[0].observation is not None
    assert trace.steps[0].observation.width == 1280
    assert trace.steps[0].action is not None
    assert trace.steps[0].action.y == 84.5
    assert trace.start_time == datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


def test_missing_observation_still_parses() -> None:
    data = complete_trace_data()
    data["steps"][0]["observation"] = None

    trace = Trace.model_validate(data)

    assert trace.steps[0].observation is None
    assert trace.steps[0].action is not None


def test_missing_post_state_still_parses() -> None:
    data = complete_trace_data()
    del data["steps"][0]["post_state"]

    trace = Trace.model_validate(data)

    assert trace.steps[0].post_state is None
    assert trace.steps[0].execution is not None


def test_action_optional_fields_can_be_missing() -> None:
    data = complete_trace_data()
    data["steps"][0]["action"] = {
        "action_id": "action-002",
        "type": "wait",
    }

    trace = Trace.model_validate(data)

    assert trace.steps[0].action is not None
    assert trace.steps[0].action.action_id == "action-002"
    assert trace.steps[0].action.x is None
    assert trace.steps[0].action.target is None


def test_metadata_preserves_json_compatible_data() -> None:
    trace = Trace.model_validate(complete_trace_data())

    assert trace.metadata["browser"] == "chromium"
    assert trace.metadata["attempt"] == 1
    assert trace.metadata["flags"] == ["vision", "computer-use"]
    assert trace.metadata["nested"] == {"ok": True, "score": 0.98, "none": None}
    assert trace.steps[0].post_state is not None
    assert trace.steps[0].post_state.state_metadata["timing_ms"] == 250


def test_trace_serializes_and_reparses() -> None:
    trace = Trace.model_validate(complete_trace_data())
    dumped = trace.model_dump_json()
    reparsed = Trace.model_validate_json(dumped)

    assert reparsed == trace
    assert reparsed.steps[0].post_state is not None
    assert reparsed.steps[0].post_state.url == "https://example.com/docs"


@pytest.mark.parametrize(
    "patch",
    [
        {"steps": {"not": "a-list"}},
        {"steps": [{"observation": {"width": "1280"}}]},
        {"steps": [{"action": {"x": "42"}}]},
    ],
)
def test_invalid_data_types_are_rejected(patch: dict) -> None:
    data = complete_trace_data()
    data.update(patch)

    with pytest.raises(ValidationError):
        Trace.model_validate(data)


def test_finding_builds_correctly() -> None:
    finding = Finding(
        rule_id="MMTRACE_TEST",
        severity=Severity.WARNING,
        step_id=None,
        title="Missing post-state",
        evidence={"step_id": "step-001", "missing": ["post_state"]},
        explanation="The trace did not include post-state evidence.",
        suggestion="Capture an observation after the action.",
    )

    assert finding.rule_id == "MMTRACE_TEST"
    assert finding.severity is Severity.WARNING
    assert finding.step_id is None
    assert finding.evidence == {"step_id": "step-001", "missing": ["post_state"]}


def test_error_finding_generates_fail_report() -> None:
    findings = [
        Finding(
            rule_id="MMTRACE_TEST",
            severity=Severity.ERROR,
            title="Action failed",
            evidence={"status": "error"},
        )
    ]

    report = Report.from_findings("trace-001", findings)

    assert report.status is ReportStatus.FAIL
    assert report.error_count == 1
    assert report.warning_count == 0
    assert report.info_count == 0


def test_warning_and_info_only_generates_pass_report() -> None:
    findings = [
        Finding(rule_id="WARN", severity=Severity.WARNING, title="Weak signal"),
        Finding(rule_id="INFO", severity=Severity.INFO, title="Extra context"),
    ]

    report = Report.from_findings("trace-001", findings)

    assert report.status is ReportStatus.PASS
    assert report.error_count == 0
    assert report.warning_count == 1
    assert report.info_count == 1


def test_report_counts_are_correct() -> None:
    findings = [
        Finding(rule_id="ERROR_1", severity=Severity.ERROR, title="First error"),
        Finding(rule_id="ERROR_2", severity=Severity.ERROR, title="Second error"),
        Finding(rule_id="WARNING_1", severity=Severity.WARNING, title="Warning"),
        Finding(rule_id="INFO_1", severity=Severity.INFO, title="Info"),
    ]

    report = Report.from_findings("trace-001", findings)

    assert report.status is ReportStatus.FAIL
    assert report.error_count == 2
    assert report.warning_count == 1
    assert report.info_count == 1
    assert report.findings == findings


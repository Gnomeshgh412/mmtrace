from mmtrace.engine import CheckEngine
from mmtrace.schema.finding import ReportStatus
from mmtrace.schema.trace import Trace


def trace_with_steps(steps: list[dict]) -> Trace:
    return Trace.model_validate({"trace_id": "trace-engine", "steps": steps})


def test_engine_returns_pass_report_for_normal_trace() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {"observation_id": "obs-001"},
                "model_input": {
                    "model_call_id": "call-001",
                    "observation_ids": ["obs-001"],
                },
            }
        ]
    )

    report = CheckEngine().run(trace)

    assert report.status is ReportStatus.PASS
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.info_count == 0
    assert report.findings == []


def test_engine_returns_fail_report_for_one_missing_observation() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "click"},
            }
        ]
    )

    report = CheckEngine().run(trace)

    assert report.status is ReportStatus.FAIL
    assert report.error_count == 1
    assert report.warning_count == 0
    assert report.info_count == 0
    assert report.findings[0].rule_id == "MMTRACE001"


def test_engine_counts_multiple_missing_observations() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "drag"},
            },
            {
                "step_id": "step-002",
                "observation": None,
                "action": {"action_id": "action-002", "type": "click"},
            },
            {
                "step_id": "step-003",
                "observation": {"observation_id": "obs-003"},
                "action": {"action_id": "action-003", "type": "click"},
            },
        ]
    )

    report = CheckEngine().run(trace)

    assert report.status is ReportStatus.FAIL
    assert report.error_count == 2
    assert report.warning_count == 0
    assert report.info_count == 0
    assert [finding.step_id for finding in report.findings] == ["step-001", "step-002"]


def test_engine_with_empty_custom_checks_returns_pass_report() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "model_input": {"model_call_id": "call-001"},
            }
        ]
    )

    report = CheckEngine(checks=[]).run(trace)

    assert report.status is ReportStatus.PASS
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.info_count == 0
    assert report.findings == []


def test_engine_default_checks_are_loaded_in_stable_order() -> None:
    engine = CheckEngine()

    assert [check.rule_id for check in engine.checks] == [
        "MMTRACE001",
        "MMTRACE002",
        "MMTRACE003",
        "MMTRACE004",
        "MMTRACE005",
        "MMTRACE006",
    ]


def test_engine_reports_multiple_rules_in_one_trace() -> None:
    trace = Trace.model_validate(
        {
            "trace_id": "trace-engine",
            "steps": [
                    {
                        "step_id": "step-001",
                        "observation": None,
                        "action": {"action_id": "action-001", "type": "move"},
                    },
                {
                    "step_id": "step-002",
                    "observation": {"observation_id": "obs-002"},
                    "model_input": {
                        "model_call_id": "call-002",
                        "observation_ids": ["obs-other"],
                    },
                },
                {
                    "step_id": "step-003",
                    "observation": {
                        "observation_id": "obs-003",
                        "viewport_width": 100,
                        "viewport_height": 100,
                    },
                    "action": {
                        "action_id": "action-003",
                        "type": "click",
                        "x": 100,
                        "y": 50,
                        "coordinate_space": "viewport",
                    },
                },
                {
                    "step_id": "step-setup",
                    "post_state": {
                        "observation": {
                            "observation_id": "obs-newer",
                            "timestamp": "2026-09-26T10:00:05Z",
                        }
                    },
                },
                {
                    "step_id": "step-004",
                    "observation": {
                        "observation_id": "obs-old",
                        "timestamp": "2026-09-26T10:00:00Z",
                    },
                    "action": {
                        "action_id": "action-004",
                        "type": "move",
                        "timestamp": "2026-09-26T10:00:10Z",
                    },
                },
                {
                    "step_id": "step-005",
                    "observation": {"observation_id": "obs-005"},
                    "action": {"action_id": "action-005", "type": "click"},
                    "execution": {"status": "success"},
                },
            ],
        }
    )

    report = CheckEngine().run(trace)

    assert report.status is ReportStatus.FAIL
    assert report.error_count == 3
    assert report.warning_count == 2
    assert report.info_count == 0
    assert [finding.rule_id for finding in report.findings] == [
        "MMTRACE001",
        "MMTRACE002",
        "MMTRACE003",
        "MMTRACE005",
        "MMTRACE006",
    ]

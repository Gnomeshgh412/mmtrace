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
from mmtrace.schema.finding import Severity
from mmtrace.schema.trace import Trace


def trace_with_steps(steps: list[dict]) -> Trace:
    return Trace.model_validate({"trace_id": "trace-checks", "steps": steps})


def test_mmtrace001_does_not_fire_when_observation_and_model_input_exist() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {"observation_id": "obs-001", "width": 1280, "height": 720},
                "model_input": {"model_call_id": "call-001", "model": "example"},
            }
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert findings == []


def test_mmtrace001_does_not_fire_when_only_model_input_exists() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "model_input": {"model_call_id": "call-001", "model": "example"},
            }
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert findings == []


def test_mmtrace001_fires_when_observation_missing_and_click_exists() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "click"},
            }
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE001"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].step_id == "step-001"
    assert findings[0].evidence == {
        "has_observation": False,
        "has_model_input": False,
        "has_action": True,
        "action_type": "click",
    }


def test_mmtrace001_fires_when_observation_missing_and_drag_exists() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "drag"},
            }
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE001"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].step_id == "step-001"
    assert findings[0].evidence["action_type"] == "drag"


def test_mmtrace001_fires_when_observation_missing_and_move_exists() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "move"},
            }
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE001"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].step_id == "step-001"
    assert findings[0].evidence["action_type"] == "move"


def test_mmtrace001_does_not_fire_for_navigate_without_observation() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "navigate"},
            }
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert findings == []


def test_mmtrace001_does_not_fire_for_done_without_observation() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "done"},
            }
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert findings == []


def test_mmtrace001_skips_unknown_action_without_observation() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "unknown_action"},
            }
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert findings == []


def test_mmtrace001_does_not_fire_when_step_has_no_decision_or_action() -> None:
    trace = trace_with_steps([{"step_id": "step-001", "observation": None}])

    findings = MissingObservationCheck().run(trace)

    assert findings == []


def test_mmtrace001_reports_each_bad_step_independently() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": None,
                "action": {"action_id": "action-001", "type": "click"},
            },
            {
                "step_id": "step-002",
                "observation": {"observation_id": "obs-002"},
                "model_input": {"model_call_id": "call-002"},
            },
            {
                "step_id": "step-003",
                "observation": None,
                "action": {"action_id": "action-003", "type": "drag"},
            },
        ]
    )

    findings = MissingObservationCheck().run(trace)

    assert [finding.step_id for finding in findings] == ["step-001", "step-003"]
    assert [finding.rule_id for finding in findings] == ["MMTRACE001", "MMTRACE001"]
    assert [finding.severity for finding in findings] == [Severity.ERROR, Severity.ERROR]
    assert findings[0].evidence == {
        "has_observation": False,
        "has_model_input": False,
        "has_action": True,
        "action_type": "click",
    }
    assert findings[1].evidence == {
        "has_observation": False,
        "has_model_input": False,
        "has_action": True,
        "action_type": "drag",
    }


def test_mmtrace002_does_not_fire_when_observation_is_in_model_context() -> None:
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

    findings = ObservationNotInModelContextCheck().run(trace)

    assert findings == []


def test_mmtrace002_fires_when_observation_is_not_in_model_context() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {"observation_id": "obs-001"},
                "model_input": {
                    "model_call_id": "call-001",
                    "observation_ids": ["obs-other"],
                },
            }
        ]
    )

    findings = ObservationNotInModelContextCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE002"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].step_id == "step-001"
    assert findings[0].evidence == {
        "observation_id": "obs-001",
        "model_call_id": "call-001",
        "model_observation_ids": ["obs-other"],
    }


def test_mmtrace003_does_not_fire_for_valid_viewport_coordinates() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-001",
                    "viewport_width": 1280,
                    "viewport_height": 720,
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "x": 1279,
                    "y": 719,
                    "coordinate_space": "viewport",
                },
            }
        ]
    )

    findings = CoordinateOutOfFrameCheck().run(trace)

    assert findings == []


def test_mmtrace003_fires_for_out_of_frame_coordinates() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-001",
                    "viewport_width": 1280,
                    "viewport_height": 720,
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "x": 1280,
                    "y": 10,
                    "coordinate_space": "viewport",
                },
            }
        ]
    )

    findings = CoordinateOutOfFrameCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE003"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].evidence == {
        "x": 1280,
        "y": 10,
        "frame_width": 1280,
        "frame_height": 720,
        "coordinate_space": "viewport",
    }


def test_mmtrace003_skips_when_coordinates_are_missing() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-001",
                    "viewport_width": 1280,
                    "viewport_height": 720,
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "coordinate_space": "viewport",
                },
            }
        ]
    )

    findings = CoordinateOutOfFrameCheck().run(trace)

    assert findings == []


def test_mmtrace004_does_not_fire_when_coordinate_space_matches() -> None:
    trace = Trace.model_validate(
        {
            "trace_id": "trace-checks",
            "metadata": {"expected_coordinate_space": "viewport"},
            "steps": [
                {
                    "step_id": "step-001",
                    "observation": {
                        "observation_id": "obs-001",
                        "viewport_width": 1280,
                        "viewport_height": 720,
                    },
                    "action": {
                        "action_id": "action-001",
                        "type": "click",
                        "x": 10,
                        "y": 20,
                        "coordinate_space": "viewport",
                    },
                }
            ],
        }
    )

    findings = CoordinateSpaceMismatchCheck().run(trace)

    assert findings == []


def test_mmtrace004_fires_for_explicit_mismatch_without_transform() -> None:
    trace = Trace.model_validate(
        {
            "trace_id": "trace-checks",
            "metadata": {"expected_coordinate_space": "image"},
            "steps": [
                {
                    "step_id": "step-001",
                    "observation": {
                        "observation_id": "obs-001",
                        "width": 1280,
                        "height": 720,
                        "viewport_width": 640,
                        "viewport_height": 360,
                    },
                    "action": {
                        "action_id": "action-001",
                        "type": "click",
                        "x": 10,
                        "y": 20,
                        "coordinate_space": "viewport",
                    },
                }
            ],
        }
    )

    findings = CoordinateSpaceMismatchCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE004"
    assert findings[0].severity is Severity.ERROR
    assert findings[0].evidence == {
        "action_coordinate_space": "viewport",
        "expected_coordinate_space": "image",
        "available_transform": None,
    }


def test_mmtrace004_skips_when_expected_space_is_unknown() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-001",
                    "width": 1280,
                    "height": 720,
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "x": 10,
                    "y": 20,
                    "coordinate_space": "viewport",
                },
            }
        ]
    )

    findings = CoordinateSpaceMismatchCheck().run(trace)

    assert findings == []


def test_mmtrace005_does_not_fire_without_newer_observation() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-001",
                    "timestamp": "2026-09-26T10:00:00Z",
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "timestamp": "2026-09-26T10:00:10Z",
                },
            }
        ]
    )

    findings = StaleObservationCheck().run(trace)

    assert findings == []


def test_mmtrace005_fires_when_newer_observation_exists_before_action() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-setup",
                "post_state": {
                    "observation": {
                        "observation_id": "obs-002",
                        "timestamp": "2026-09-26T10:00:05Z",
                    }
                },
            },
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-001",
                    "timestamp": "2026-09-26T10:00:00Z",
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "timestamp": "2026-09-26T10:00:10Z",
                },
            },
        ]
    )

    findings = StaleObservationCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE005"
    assert findings[0].severity is Severity.WARNING
    assert findings[0].evidence == {
        "used_observation_id": "obs-001",
        "used_observation_timestamp": "2026-09-26T10:00:00+00:00",
        "newer_observation_id": "obs-002",
        "newer_observation_timestamp": "2026-09-26T10:00:05+00:00",
        "action_timestamp": "2026-09-26T10:00:10+00:00",
    }


def test_mmtrace005_does_not_use_time_threshold_without_new_observation() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-001",
                    "timestamp": "2026-09-26T10:00:00Z",
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "timestamp": "2026-09-26T11:00:00Z",
                },
            }
        ]
    )

    findings = StaleObservationCheck().run(trace)

    assert findings == []


def test_mmtrace006_does_not_fire_when_success_has_post_state() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "action": {"action_id": "action-001", "type": "click"},
                "execution": {"status": "success"},
                "post_state": {"url": "https://example.com/next"},
            }
        ]
    )

    findings = MissingPostActionVerificationCheck().run(trace)

    assert findings == []


def test_mmtrace006_fires_when_success_has_no_post_state() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "action": {"action_id": "action-001", "type": "click"},
                "execution": {"status": "success"},
            }
        ]
    )

    findings = MissingPostActionVerificationCheck().run(trace)

    assert len(findings) == 1
    assert findings[0].rule_id == "MMTRACE006"
    assert findings[0].severity is Severity.WARNING
    assert findings[0].evidence == {
        "action_type": "click",
        "execution_status": "success",
        "has_post_state": False,
    }


def test_mmtrace006_does_not_fire_when_execution_failed() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "step-001",
                "action": {"action_id": "action-001", "type": "click"},
                "execution": {"status": "failed"},
            }
        ]
    )

    findings = MissingPostActionVerificationCheck().run(trace)

    assert findings == []

from pathlib import Path

from mmtrace.adapters.browser_use import BrowserUseAdapter
from mmtrace.adapters.holo4 import Holo4Adapter
from mmtrace.adapters.osworld import OSWorldAdapter
from mmtrace.engine import CheckEngine
from mmtrace.evaluation import EvaluationCoverage, EvaluationEngine, EvaluationOutcome
from mmtrace.schema.finding import Severity
from mmtrace.schema.trace import Trace

EXAMPLES = Path(__file__).parents[1] / "examples"


def trace_with_steps(steps: list[dict], metadata: dict | None = None) -> Trace:
    return Trace.model_validate(
        {"trace_id": "trace-evaluation", "metadata": metadata or {}, "steps": steps}
    )


def evaluations_by_rule(trace: Trace):
    report = CheckEngine().run(trace)
    evaluations = EvaluationEngine().evaluate(trace, report.findings)
    return {evaluation.rule_id: evaluation for evaluation in evaluations}, report


def test_mmtrace001_full_pass_for_click_with_observation() -> None:
    trace = trace_with_steps(
        [{"step_id": "s1", "observation": {"observation_id": "o1"}, "action": {"type": "click"}}]
    )

    evaluation, report = evaluations_by_rule(trace)

    assert report.findings == []
    assert evaluation["MMTRACE001"].coverage is EvaluationCoverage.FULL
    assert evaluation["MMTRACE001"].outcome is EvaluationOutcome.PASS
    assert evaluation["MMTRACE001"].applicable_units == 1
    assert evaluation["MMTRACE001"].evaluable_units == 1


def test_mmtrace001_missing_observation_is_evaluable_error() -> None:
    trace = trace_with_steps(
        [{"step_id": "s1", "observation": None, "action": {"type": "click"}}]
    )

    evaluation, report = evaluations_by_rule(trace)

    assert [finding.rule_id for finding in report.findings] == ["MMTRACE001"]
    assert evaluation["MMTRACE001"].coverage is EvaluationCoverage.FULL
    assert evaluation["MMTRACE001"].outcome is EvaluationOutcome.ERROR
    assert evaluation["MMTRACE001"].finding_count == 1
    assert evaluation["MMTRACE001"].not_evaluable_units == 0


def test_mmtrace001_navigation_without_observation_is_not_applicable() -> None:
    trace = trace_with_steps(
        [{"step_id": "s1", "observation": None, "action": {"type": "navigate"}}]
    )

    evaluation, _ = evaluations_by_rule(trace)

    assert evaluation["MMTRACE001"].coverage is EvaluationCoverage.NOT_APPLICABLE
    assert evaluation["MMTRACE001"].outcome is EvaluationOutcome.NONE
    assert evaluation["MMTRACE001"].applicable_units == 0


def test_mmtrace001_mixed_counts_are_full_error() -> None:
    trace = trace_with_steps(
        [
            {"step_id": "s1", "observation": {"observation_id": "o1"}, "action": {"type": "click"}},
            {"step_id": "s2", "observation": None, "action": {"type": "drag"}},
            {"step_id": "s3", "observation": None, "action": {"type": "navigate"}},
        ]
    )

    evaluation, _ = evaluations_by_rule(trace)

    assert evaluation["MMTRACE001"].coverage is EvaluationCoverage.FULL
    assert evaluation["MMTRACE001"].outcome is EvaluationOutcome.ERROR
    assert evaluation["MMTRACE001"].applicable_units == 2
    assert evaluation["MMTRACE001"].evaluable_units == 2


def test_mmtrace002_empty_observation_ids_is_evaluable_error() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "s1",
                "observation": {"observation_id": "o1"},
                "model_input": {"observation_ids": []},
            }
        ]
    )

    evaluation, _ = evaluations_by_rule(trace)

    assert evaluation["MMTRACE002"].coverage is EvaluationCoverage.FULL
    assert evaluation["MMTRACE002"].outcome is EvaluationOutcome.ERROR
    assert evaluation["MMTRACE002"].finding_count == 1


def test_mmtrace002_missing_model_input_is_not_evaluable() -> None:
    trace = trace_with_steps([{"step_id": "s1", "observation": {"observation_id": "o1"}}])

    evaluation, report = evaluations_by_rule(trace)

    assert report.findings == []
    assert evaluation["MMTRACE002"].coverage is EvaluationCoverage.NOT_EVALUABLE
    assert evaluation["MMTRACE002"].outcome is EvaluationOutcome.NONE
    assert evaluation["MMTRACE002"].missing_evidence[0].code == "model_input"


def test_mmtrace002_mixed_evidence_is_partial() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "s1",
                "observation": {"observation_id": "o1"},
                "model_input": {"observation_ids": ["o1"]},
            },
            {"step_id": "s2", "observation": {"observation_id": "o2"}},
        ]
    )

    evaluation, _ = evaluations_by_rule(trace)

    assert evaluation["MMTRACE002"].coverage is EvaluationCoverage.PARTIAL
    assert evaluation["MMTRACE002"].outcome is EvaluationOutcome.PASS
    assert evaluation["MMTRACE002"].applicable_units == 2
    assert evaluation["MMTRACE002"].evaluable_units == 1


def test_mmtrace003_coordinate_boundaries_and_missing_dimensions() -> None:
    traces = {
        "inside": trace_with_steps(
            [
                {
                    "step_id": "s1",
                    "observation": {"viewport_width": 10, "viewport_height": 10},
                    "action": {"type": "click", "x": 9, "y": 9, "coordinate_space": "viewport"},
                }
            ]
        ),
        "x_equals_width": trace_with_steps(
            [
                {
                    "step_id": "s1",
                    "observation": {"viewport_width": 10, "viewport_height": 10},
                    "action": {"type": "click", "x": 10, "y": 9, "coordinate_space": "viewport"},
                }
            ]
        ),
        "negative": trace_with_steps(
            [
                {
                    "step_id": "s1",
                    "observation": {"viewport_width": 10, "viewport_height": 10},
                    "action": {"type": "click", "x": -1, "y": 9, "coordinate_space": "viewport"},
                }
            ]
        ),
        "missing_dimensions": trace_with_steps(
            [{"step_id": "s1", "observation": {}, "action": {"type": "click", "x": 1, "y": 1}}]
        ),
    }

    assert evaluations_by_rule(traces["inside"])[0]["MMTRACE003"].outcome is EvaluationOutcome.PASS
    assert evaluations_by_rule(traces["x_equals_width"])[0]["MMTRACE003"].outcome is EvaluationOutcome.ERROR
    assert evaluations_by_rule(traces["negative"])[0]["MMTRACE003"].outcome is EvaluationOutcome.ERROR
    missing = evaluations_by_rule(traces["missing_dimensions"])[0]["MMTRACE003"]
    assert missing.coverage is EvaluationCoverage.NOT_EVALUABLE
    assert missing.outcome is EvaluationOutcome.NONE
    assert missing.missing_evidence[0].code == "observation.frame_dimensions"


def test_no_finding_does_not_imply_pass_when_evidence_missing() -> None:
    trace = trace_with_steps(
        [{"step_id": "s1", "observation": {}, "action": {"type": "click", "x": 1, "y": 1}}]
    )

    evaluation, report = evaluations_by_rule(trace)

    assert [finding for finding in report.findings if finding.rule_id == "MMTRACE003"] == []
    assert evaluation["MMTRACE003"].coverage is EvaluationCoverage.NOT_EVALUABLE
    assert evaluation["MMTRACE003"].outcome is EvaluationOutcome.NONE


def test_partial_pass_is_not_full_pass() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "s1",
                "observation": {"viewport_width": 10, "viewport_height": 10},
                "action": {"type": "click", "x": 1, "y": 1, "coordinate_space": "viewport"},
            },
            {
                "step_id": "s2",
                "observation": {},
                "action": {"type": "click", "x": 1, "y": 1, "coordinate_space": "viewport"},
            },
        ]
    )

    evaluation, _ = evaluations_by_rule(trace)

    assert evaluation["MMTRACE003"].coverage is EvaluationCoverage.PARTIAL
    assert evaluation["MMTRACE003"].outcome is EvaluationOutcome.PASS
    assert evaluation["MMTRACE003"].finding_count == 0


def test_error_and_partial_coverage_can_coexist() -> None:
    trace = trace_with_steps(
        [
            {
                "step_id": "s1",
                "observation": {"viewport_width": 10, "viewport_height": 10},
                "action": {"type": "click", "x": 10, "y": 1, "coordinate_space": "viewport"},
            },
            {
                "step_id": "s2",
                "observation": {},
                "action": {"type": "click", "x": 1, "y": 1, "coordinate_space": "viewport"},
            },
        ]
    )

    evaluation, _ = evaluations_by_rule(trace)

    assert evaluation["MMTRACE003"].coverage is EvaluationCoverage.PARTIAL
    assert evaluation["MMTRACE003"].outcome is EvaluationOutcome.ERROR
    assert evaluation["MMTRACE003"].finding_count == 1


def test_not_applicable_when_rule_has_no_units() -> None:
    trace = trace_with_steps([{"step_id": "s1", "action": {"type": "scroll"}}])

    evaluation, _ = evaluations_by_rule(trace)

    assert evaluation["MMTRACE003"].coverage is EvaluationCoverage.NOT_APPLICABLE
    assert evaluation["MMTRACE003"].outcome is EvaluationOutcome.NONE


def test_missing_evidence_is_aggregated_by_code_in_trace_order() -> None:
    trace = trace_with_steps(
        [
            {"step_id": "s1", "observation": {}, "action": {"type": "click", "x": 1, "y": 1}},
            {"step_id": "s2", "observation": {}, "action": {"type": "move", "x": 2, "y": 2}},
            {"step_id": "s3", "observation": {}, "action": {"type": "drag", "x": 3, "y": 3}},
            {"step_id": "s4", "observation": {}, "action": {"type": "click", "x": 4, "y": 4}},
        ]
    )

    evaluation, _ = evaluations_by_rule(trace)
    missing = evaluation["MMTRACE003"].missing_evidence

    assert len(missing) == 1
    assert missing[0].code == "observation.frame_dimensions"
    assert missing[0].count == 4
    assert missing[0].step_ids == ["s1", "s2", "s3", "s4"]


def test_mmtrace004_matching_mismatch_transform_and_missing_evidence() -> None:
    matching = trace_with_steps(
        [
            {
                "step_id": "s1",
                "observation": {"viewport_width": 10, "viewport_height": 10},
                "action": {"type": "click", "x": 1, "y": 1, "coordinate_space": "viewport"},
            }
        ],
        metadata={"expected_coordinate_space": "viewport"},
    )
    mismatch = matching.model_copy(deep=True)
    mismatch.metadata["expected_coordinate_space"] = "image"
    transform = mismatch.model_copy(deep=True)
    transform.metadata["coordinate_transform"] = {"scale": 0.5}
    no_action_space = matching.model_copy(deep=True)
    no_action_space.steps[0].action.coordinate_space = None
    no_executor_space = trace_with_steps(
        [
            {
                "step_id": "s1",
                "observation": {"viewport_width": 10, "viewport_height": 10},
                "action": {"type": "click", "x": 1, "y": 1, "coordinate_space": "viewport"},
            }
        ]
    )
    non_coordinate = trace_with_steps([{"step_id": "s1", "action": {"type": "scroll"}}])

    assert evaluations_by_rule(matching)[0]["MMTRACE004"].outcome is EvaluationOutcome.PASS
    assert evaluations_by_rule(mismatch)[0]["MMTRACE004"].outcome is EvaluationOutcome.ERROR
    assert evaluations_by_rule(transform)[0]["MMTRACE004"].outcome is EvaluationOutcome.PASS
    assert evaluations_by_rule(no_action_space)[0]["MMTRACE004"].missing_evidence[0].code == "action.coordinate_space"
    assert evaluations_by_rule(no_executor_space)[0]["MMTRACE004"].missing_evidence[0].code == "executor.coordinate_space"
    assert evaluations_by_rule(non_coordinate)[0]["MMTRACE004"].coverage is EvaluationCoverage.NOT_APPLICABLE


def test_mmtrace005_pass_warning_not_evaluable_and_partial_warning() -> None:
    no_newer = trace_with_steps(
        [
            {
                "step_id": "s1",
                "observation": {"observation_id": "a", "timestamp": "2026-09-26T10:00:00Z"},
                "action": {"type": "click", "timestamp": "2026-09-26T10:00:10Z"},
            }
        ]
    )
    stale = trace_with_steps(
        [
            {
                "step_id": "setup",
                "post_state": {
                    "observation": {"observation_id": "b", "timestamp": "2026-09-26T10:00:05Z"}
                },
            },
            {
                "step_id": "s1",
                "observation": {"observation_id": "a", "timestamp": "2026-09-26T10:00:00Z"},
                "action": {"type": "click", "timestamp": "2026-09-26T10:00:10Z"},
            },
        ]
    )
    obs_timestamp_missing = trace_with_steps(
        [{"step_id": "s1", "observation": {"observation_id": "a"}, "action": {"type": "click", "timestamp": "2026-09-26T10:00:10Z"}}]
    )
    action_timestamp_missing = trace_with_steps(
        [{"step_id": "s1", "observation": {"observation_id": "a", "timestamp": "2026-09-26T10:00:00Z"}, "action": {"type": "click"}}]
    )
    mixed = stale.model_copy(deep=True)
    mixed.steps.append(
        Trace.model_validate(
            {
                "steps": [
                    {"step_id": "s2", "observation": {"observation_id": "c"}, "action": {"type": "click"}}
                ]
            }
        ).steps[0]
    )

    assert evaluations_by_rule(no_newer)[0]["MMTRACE005"].outcome is EvaluationOutcome.PASS
    assert evaluations_by_rule(stale)[0]["MMTRACE005"].outcome is EvaluationOutcome.WARNING
    assert evaluations_by_rule(obs_timestamp_missing)[0]["MMTRACE005"].missing_evidence[0].code == "observation.timestamp"
    assert evaluations_by_rule(action_timestamp_missing)[0]["MMTRACE005"].missing_evidence[0].code == "action.timestamp"
    mixed_eval = evaluations_by_rule(mixed)[0]["MMTRACE005"]
    assert mixed_eval.outcome is EvaluationOutcome.WARNING
    assert mixed_eval.coverage is EvaluationCoverage.PARTIAL


def test_mmtrace006_status_semantics() -> None:
    trace = trace_with_steps(
        [
            {"step_id": "success-post", "action": {"type": "click"}, "execution": {"status": "success"}, "post_state": {"url": "https://example.test"}},
            {"step_id": "success-missing", "action": {"type": "click"}, "execution": {"status": "success"}},
            {"step_id": "missing-execution", "action": {"type": "click"}},
            {"step_id": "unknown", "action": {"type": "click"}, "execution": {"status": "unknown"}},
            {"step_id": "failed", "action": {"type": "click"}, "execution": {"status": "failed"}},
            {"step_id": "non-state-changing", "action": {"type": "scroll"}, "execution": {"status": "success"}},
        ]
    )

    evaluation, _ = evaluations_by_rule(trace)
    rule = evaluation["MMTRACE006"]

    assert rule.outcome is EvaluationOutcome.WARNING
    assert rule.coverage is EvaluationCoverage.PARTIAL
    assert rule.applicable_units == 4
    assert rule.evaluable_units == 2
    assert rule.finding_count == 1
    assert [(missing.code, missing.count) for missing in rule.missing_evidence] == [
        ("execution", 1),
        ("execution.status", 1),
    ]


def test_mmtrace007_status_semantics_and_partial_error() -> None:
    trace = trace_with_steps(
        [
            {"step_id": "success", "action": {"type": "shell"}, "execution": {"status": "success"}},
            {"step_id": "failed", "action": {"type": "shell"}, "execution": {"status": "failed"}},
            {"step_id": "missing-execution", "action": {"type": "shell"}},
            {"step_id": "unknown", "action": {"type": "shell"}, "execution": {"status": "unknown"}},
            {"step_id": "no-action", "execution": {"status": "failed"}},
        ]
    )

    evaluation, _ = evaluations_by_rule(trace)
    rule = evaluation["MMTRACE007"]

    assert rule.outcome is EvaluationOutcome.ERROR
    assert rule.coverage is EvaluationCoverage.PARTIAL
    assert rule.applicable_units == 4
    assert rule.evaluable_units == 2
    assert rule.finding_count == 1


def test_finding_evaluation_consistency_for_all_rules() -> None:
    trace = trace_with_steps(
        [
            {"step_id": "s1", "observation": None, "action": {"type": "move"}},
            {"step_id": "s2", "observation": {"observation_id": "o2"}, "model_input": {"observation_ids": []}},
            {
                "step_id": "s3",
                "observation": {"viewport_width": 10, "viewport_height": 10},
                "action": {"type": "click", "x": 10, "y": 1, "coordinate_space": "viewport"},
            },
            {
                "step_id": "s4",
                "observation": {"width": 10, "height": 10, "viewport_width": 10, "viewport_height": 10},
                "action": {"type": "click", "x": 1, "y": 1, "coordinate_space": "viewport"},
            },
            {
                "step_id": "setup",
                "post_state": {"observation": {"observation_id": "newer", "timestamp": "2026-09-26T10:00:05Z"}},
            },
            {
                "step_id": "s5",
                "observation": {"observation_id": "old", "timestamp": "2026-09-26T10:00:00Z"},
                "action": {"type": "move", "timestamp": "2026-09-26T10:00:10Z"},
            },
            {"step_id": "s6", "action": {"type": "click"}, "execution": {"status": "success"}},
            {"step_id": "s7", "action": {"type": "shell"}, "execution": {"status": "failed"}},
            {"step_id": "s8", "observation": {}, "action": {"type": "click", "x": 1, "y": 1}},
        ],
        metadata={"expected_coordinate_space": "image"},
    )

    evaluations, report = evaluations_by_rule(trace)

    for rule_id, evaluation in evaluations.items():
        rule_findings = [finding for finding in report.findings if finding.rule_id == rule_id]
        if evaluation.outcome is EvaluationOutcome.ERROR:
            assert any(finding.severity is Severity.ERROR for finding in rule_findings)
        if evaluation.outcome is EvaluationOutcome.WARNING:
            assert any(finding.severity is Severity.WARNING for finding in rule_findings)
        if evaluation.finding_count == 0 and evaluation.evaluable_units > 0:
            assert evaluation.outcome is EvaluationOutcome.PASS
        if evaluation.evaluable_units == 0:
            assert evaluation.outcome is EvaluationOutcome.NONE
        assert evaluation.finding_count == len(rule_findings)


def test_real_examples_evaluability_smoke() -> None:
    holo4 = Holo4Adapter().load(EXAMPLES / "holo4_real_execution_failure" / "trajectory.json")
    browser_use = BrowserUseAdapter().load(EXAMPLES / "browser_use_real" / "history.json")
    osworld = OSWorldAdapter().load(EXAMPLES / "osworld_real_failure" / "traj.jsonl")

    holo4_evaluations, _ = evaluations_by_rule(holo4)
    browser_evaluations, _ = evaluations_by_rule(browser_use)
    osworld_evaluations, _ = evaluations_by_rule(osworld)

    assert holo4_evaluations["MMTRACE007"].finding_count == 5
    assert holo4_evaluations["MMTRACE007"].outcome is EvaluationOutcome.ERROR
    assert any(
        evaluation.coverage
        in {EvaluationCoverage.NOT_EVALUABLE, EvaluationCoverage.PARTIAL}
        for evaluation in browser_evaluations.values()
    )
    assert osworld_evaluations["MMTRACE003"].outcome is EvaluationOutcome.ERROR
    assert osworld_evaluations["MMTRACE005"].outcome is EvaluationOutcome.WARNING

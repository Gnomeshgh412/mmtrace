from pathlib import Path

from mmtrace.adapters.browser_use import BrowserUseAdapter
from mmtrace.cli import main
from mmtrace.engine import CheckEngine

FIXTURES = Path(__file__).parent / "fixtures"
REAL_EXAMPLE = Path(__file__).parents[1] / "examples" / "browser_use_real" / "history.json"


def load_browser_use_fixture():
    return BrowserUseAdapter().load(FIXTURES / "browser_use_history.json")


def test_browser_use_adapter_loads_history_as_trace() -> None:
    trace = load_browser_use_fixture()

    assert trace.trace_id == "browser_use_history"
    assert trace.task == "Search documentation"
    assert trace.agent == "browser-use"
    assert trace.metadata["source"] == "browser-use"
    assert trace.metadata["source_format"] == "AgentHistoryList"
    assert trace.metadata["source_version"] == "0.test"


def test_browser_use_observation_maps_screenshot_path() -> None:
    trace = load_browser_use_fixture()

    assert trace.steps[0].observation is not None
    assert trace.steps[0].observation.observation_id == "browser-use-step-1"
    assert trace.steps[0].observation.image_path == "screenshots/step-1.png"
    assert trace.steps[0].observation.width is None
    assert trace.steps[0].observation.viewport_width is None


def test_browser_use_model_input_is_not_fabricated() -> None:
    trace = load_browser_use_fixture()

    assert all(step.model_input is None for step in trace.steps)


def test_browser_use_coordinate_click_maps_viewport_coordinates() -> None:
    trace = load_browser_use_fixture()
    action = trace.steps[1].action

    assert action is not None
    assert action.type == "click"
    assert action.x == 120
    assert action.y == 80
    assert action.coordinate_space == "viewport"


def test_browser_use_index_click_does_not_fabricate_coordinates() -> None:
    trace = load_browser_use_fixture()
    action = trace.steps[0].action

    assert action is not None
    assert action.type == "click"
    assert action.target == "3"
    assert action.x is None
    assert action.y is None
    assert action.coordinate_space is None


def test_browser_use_execution_failed_maps_error() -> None:
    trace = load_browser_use_fixture()
    execution = trace.steps[0].execution

    assert execution is not None
    assert execution.status == "failed"
    assert execution.error == "element not found"


def test_browser_use_execution_unknown_without_error_or_success() -> None:
    trace = load_browser_use_fixture()
    execution = trace.steps[1].execution

    assert execution is not None
    assert execution.status == "unknown"
    assert execution.error is None


def test_browser_use_multi_action_source_step_is_flattened() -> None:
    trace = load_browser_use_fixture()

    assert len(trace.steps) == 4
    assert [step.step_id for step in trace.steps] == ["1", "2", "3", "4"]
    assert trace.steps[0].action is not None
    assert trace.steps[0].action.action_id == "browser-use-step-1-action-0"
    assert trace.steps[1].action is not None
    assert trace.steps[1].action.action_id == "browser-use-step-1-action-1"


def test_browser_use_post_state_maps_next_state_for_single_and_last_multi_action() -> None:
    trace = load_browser_use_fixture()

    assert trace.steps[0].post_state is None
    assert trace.steps[1].post_state is not None
    assert trace.steps[1].post_state.url == "https://example.com/search"
    assert trace.steps[1].post_state.window_title == "Search"
    assert trace.steps[1].post_state.observation is not None
    assert trace.steps[1].post_state.observation.image_path == "screenshots/step-2.png"
    assert trace.steps[2].post_state is not None
    assert trace.steps[2].post_state.url == "https://example.com/search?q=MMTrace"


def test_browser_use_last_source_step_has_no_post_state() -> None:
    trace = load_browser_use_fixture()

    assert trace.steps[-1].action is not None
    assert trace.steps[-1].action.action_id == "browser-use-step-3-action-0"
    assert trace.steps[-1].post_state is None


def test_browser_use_cli_runs_end_to_end(capsys) -> None:
    exit_code = main(
        [
            "check",
            str(FIXTURES / "browser_use_history.json"),
            "--adapter",
            "browser-use",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code in {0, 1}
    assert "MMTrace Reliability Report" in captured.out
    assert captured.err == ""


def test_browser_use_real_example_does_not_flag_initial_navigate_as_missing_observation() -> None:
    trace = BrowserUseAdapter().load(REAL_EXAMPLE)
    source_action_count = _source_action_count(REAL_EXAMPLE)
    mmtrace_action_count = sum(1 for step in trace.steps if step.action is not None)

    report = CheckEngine().run(trace)
    mmtrace001_findings = [
        finding for finding in report.findings if finding.rule_id == "MMTRACE001"
    ]

    assert source_action_count == mmtrace_action_count
    assert trace.steps[0].action is not None
    assert trace.steps[0].action.type == "navigate"
    assert mmtrace001_findings == []
    assert report.error_count == 0


def _source_action_count(path: Path) -> int:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
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

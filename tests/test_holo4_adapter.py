import json
from pathlib import Path

import pytest

from mmtrace.adapters.base import AdapterError
from mmtrace.adapters.holo4 import Holo4Adapter
from mmtrace.cli import main
from mmtrace.engine import CheckEngine


def write_holo4(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def receipt(exit_code: int, text: str = "tool output") -> str:
    return (
        f"{text}\n\n"
        "[Execution receipt]\n"
        "execution_id: exec-test\n"
        "state: completed\n"
        f"exit_code: {exit_code}\n"
        "available_actions: none"
    )


def holo4_payload(*, benchmark: str = "OSWorld", model: str = "Holo4 27B") -> dict:
    return {
        "id": "libreoffice-calc-13-23ff35a8",
        "model": model,
        "benchmark": benchmark,
        "task": "libreoffice_calc_13",
        "instruction": (
            "Summarize the total revenue for each promotion type in a new sheet "
            "(Sheet2) with the promotion names as the column headers using the Pivot Table feature."
        ),
        "success": False,
        "score": 0.0,
        "steps": [],
    }


def test_holo4_adapter_maps_basic_metadata_and_does_not_fabricate_model_input(tmp_path: Path) -> None:
    payload = holo4_payload()
    payload["steps"] = [
        {
            "image": "img/libreoffice-calc-13-23ff35a8/image_018.webp",
            "calls": [{"name": "shell", "args": {"command": "echo ok"}}],
            "results": [receipt(0, "ok")],
        }
    ]
    path = write_holo4(tmp_path / "holo4.json", payload)

    trace = Holo4Adapter().load(path)

    assert trace.trace_id == "libreoffice-calc-13-23ff35a8"
    assert trace.agent == "Holo4 27B"
    assert trace.task == payload["instruction"]
    assert trace.metadata["source"] == "holo4"
    assert trace.metadata["source_format"] == "Hcompany/trajectories"
    assert trace.metadata["benchmark"] == "OSWorld"
    assert all(step.model_input is None for step in trace.steps)


def test_holo4_adapter_flattens_multiple_calls_and_preserves_provenance(tmp_path: Path) -> None:
    payload = holo4_payload()
    payload["steps"] = [
        {
            "image": "img/example/image_001.webp",
            "calls": [
                {"name": "api_search", "args": {"query": "buffer"}},
                {"name": "api_fetch", "args": {"method": "GET", "url": "https://example.test"}},
            ],
            "results": ['{"success": true}', '{"success": true}'],
        }
    ]
    path = write_holo4(tmp_path / "holo4.json", payload)

    trace = Holo4Adapter().load(path)

    assert len(trace.steps) == 2
    assert [step.action.type for step in trace.steps if step.action is not None] == [
        "api_search",
        "api_fetch",
    ]
    assert trace.steps[0].post_state is not None
    assert trace.steps[0].post_state.state_metadata == {
        "source_step": 0,
        "source_call_index": 0,
    }
    assert trace.steps[1].post_state is not None
    assert trace.steps[1].post_state.state_metadata == {
        "source_step": 0,
        "source_call_index": 1,
    }


def test_holo4_adapter_does_not_guess_coordinate_space(tmp_path: Path) -> None:
    payload = holo4_payload()
    payload["steps"] = [
        {
            "image": "img/example/image_001.webp",
            "calls": [{"name": "click_desktop", "args": {"x": 497, "y": 913}}],
            "results": [],
        }
    ]
    path = write_holo4(tmp_path / "holo4.json", payload)

    trace = Holo4Adapter().load(path)
    action = trace.steps[0].action

    assert action is not None
    assert action.type == "click"
    assert action.x == 497
    assert action.y == 913
    assert action.coordinate_space is None


def test_holo4_adapter_does_not_align_results_when_lengths_differ(tmp_path: Path) -> None:
    payload = holo4_payload()
    payload["steps"] = [
        {
            "calls": [
                {"name": "api_fetch", "args": {"url": "https://example.test/1"}},
                {"name": "api_fetch", "args": {"url": "https://example.test/2"}},
            ],
            "results": ['{"error": {"code": 404, "message": "not found"}}'],
        }
    ]
    path = write_holo4(tmp_path / "holo4.json", payload)

    trace = Holo4Adapter().load(path)

    assert [step.execution.status for step in trace.steps if step.execution is not None] == [
        "unknown",
        "unknown",
    ]


def test_holo4_real_osworld_public_case_fragment_triggers_five_mmtrace007_errors(
    tmp_path: Path,
) -> None:
    payload = holo4_payload()
    raw_failures = {
        13: "X Error of failed request: BadValue",
        15: "X Error of failed request: BadValue",
        21: "NameError: name 'pyautoguiBUTTONDOWN' is not defined",
        22: "AttributeError: module 'pyautogui' has no attribute 'buttonDown'",
        75: "IndexError: tuple index out of range",
    }
    steps = [{} for _ in range(76)]
    for source_step, error in raw_failures.items():
        steps[source_step] = {
            "image": f"img/libreoffice-calc-13-23ff35a8/image_{source_step:03d}.webp",
            "calls": [{"name": "shell", "args": {"command": "public benchmark command"}}],
            "results": [receipt(1, error)],
        }
    payload["steps"] = steps
    path = write_holo4(tmp_path / "libreoffice-calc-13-23ff35a8.json", payload)

    trace = Holo4Adapter().load(path)
    report = CheckEngine().run(trace)
    findings = [finding for finding in report.findings if finding.rule_id == "MMTRACE007"]

    assert report.status.value == "FAIL"
    assert report.error_count == 5
    assert len(findings) == 5
    assert {finding.evidence["execution_status"] for finding in findings} == {"failed"}
    assert {finding.evidence["action_type"] for finding in findings} == {"shell"}
    observed_source_steps = set()
    for finding in findings:
        step = trace.steps[int(finding.step_id) - 1]
        assert step.post_state is not None
        observed_source_steps.add(step.post_state.state_metadata["source_step"])
        assert "exit_code 1" in finding.evidence["error"]
    assert observed_source_steps == {13, 15, 21, 22, 75}


@pytest.mark.parametrize(
    ("model", "result", "expected_error"),
    [
        (
            "Holo4 27B",
            '{"error": {"code": 404, "message": "No handler for GET buffer/1/updates/list.json"}}',
            "No handler for GET buffer/1/updates/list.json",
        ),
        (
            "Holo4 35B A3B",
            '{"code": 401, "message": "No gmail account is connected to this workspace"}',
            "No gmail account is connected to this workspace",
        ),
    ],
)
def test_holo4_automationbench_errors_trigger_mmtrace007(
    tmp_path: Path,
    model: str,
    result: str,
    expected_error: str,
) -> None:
    payload = holo4_payload(benchmark="AutomationBench", model=model)
    payload["id"] = f"automation-{model}"
    payload["steps"] = [
        {
            "calls": [{"name": "api_fetch", "args": {"method": "GET", "url": "https://api.example.test"}}],
            "results": [result],
        }
    ]
    path = write_holo4(tmp_path / "automation.json", payload)

    trace = Holo4Adapter().load(path)
    report = CheckEngine().run(trace)
    findings = [finding for finding in report.findings if finding.rule_id == "MMTRACE007"]

    assert trace.agent == model
    assert len(findings) == 1
    assert findings[0].evidence["action_type"] == "api_fetch"
    assert expected_error in findings[0].evidence["error"]


@pytest.mark.parametrize(
    ("benchmark", "result"),
    [
        ("OSWorld", receipt(0, "ok")),
        ("OSWorld", "the word error appears in ordinary text"),
        ("OSWorld", '{"code": 500, "value": "ordinary business JSON"}'),
        ("AutomationBench", '{"success": true}'),
        ("AutomationBench", '{"code": 200, "message": "ok"}'),
        ("AutomationBench", "not structured"),
    ],
)
def test_holo4_negative_results_do_not_trigger_mmtrace007(
    tmp_path: Path,
    benchmark: str,
    result: str,
) -> None:
    payload = holo4_payload(benchmark=benchmark)
    payload["steps"] = [
        {
            "calls": [{"name": "api_fetch", "args": {"method": "GET", "url": "https://api.example.test"}}],
            "results": [result],
        }
    ]
    path = write_holo4(tmp_path / "negative.json", payload)

    trace = Holo4Adapter().load(path)
    report = CheckEngine().run(trace)

    assert [finding for finding in report.findings if finding.rule_id == "MMTRACE007"] == []


def test_holo4_cli_runs_adapter(capsys, tmp_path: Path) -> None:
    payload = holo4_payload(benchmark="AutomationBench")
    payload["steps"] = [
        {
            "calls": [{"name": "api_fetch", "args": {"method": "GET", "url": "https://api.example.test"}}],
            "results": ['{"error": "Spreadsheet not found"}'],
        }
    ]
    path = write_holo4(tmp_path / "holo4.json", payload)

    exit_code = main(["check", str(path), "--adapter", "holo4", "--format", "json"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert exit_code == 1
    assert parsed["status"] == "FAIL"
    assert parsed["findings"][0]["rule_id"] == "MMTRACE007"


def test_holo4_adapter_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(AdapterError, match="invalid JSON"):
        Holo4Adapter().load(path)

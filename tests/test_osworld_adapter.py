import json
from pathlib import Path

import pytest

from mmtrace.adapters.base import AdapterError
from mmtrace.adapters.osworld import OSWorldAdapter
from mmtrace.engine import CheckEngine

REAL_OSWORLD = Path(__file__).parents[1] / "examples" / "osworld_real_failure" / "traj.jsonl"


def write_png_header(path: Path, width: int = 1920, height: int = 1080) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def minimal_rows() -> list[dict]:
    response = "Action: move then drag"
    return [
        {
            "step_num": 1,
            "action_timestamp": "20260622@000001000000",
            "action": "pyautogui.moveTo(10, 20)",
            "response": response,
            "reward": 0,
            "done": False,
            "info": {},
            "screenshot_file": "step_1_20260622@000001000000.png",
        },
        {
            "step_num": 1,
            "action_timestamp": "20260622@000002000000",
            "action": "pyautogui.dragTo(30, 40, duration=0.5)",
            "response": response,
            "reward": 0,
            "done": False,
            "info": {},
            "screenshot_file": "step_1_20260622@000002000000.png",
        },
    ]


def write_minimal_osworld_dir(tmp_path: Path) -> Path:
    write_png_header(tmp_path / "step_0_20260622@000000000000.png")
    write_png_header(tmp_path / "step_1_20260622@000001000000.png")
    write_png_header(tmp_path / "step_1_20260622@000002000000.png")
    (tmp_path / "instruction.txt").write_text("Do the thing.", encoding="utf-8")
    (tmp_path / "result.txt").write_text("0.0\n", encoding="utf-8")
    path = tmp_path / "traj.jsonl"
    write_jsonl(path, minimal_rows())
    return path


def test_osworld_adapter_loads_minimal_valid_trajectory(tmp_path: Path) -> None:
    path = write_minimal_osworld_dir(tmp_path)

    trace = OSWorldAdapter().load(path)

    assert trace.trace_id == f"osworld-{tmp_path.name}"
    assert trace.task == "Do the thing."
    assert trace.metadata["source"] == "osworld"
    assert trace.metadata["task_result"] == "0.0"
    assert len(trace.steps) == 2


def test_osworld_adapter_parses_actions_coordinates_and_post_state(tmp_path: Path) -> None:
    path = write_minimal_osworld_dir(tmp_path)

    trace = OSWorldAdapter().load(path)

    first = trace.steps[0]
    second = trace.steps[1]
    assert first.action is not None
    assert first.action.type == "move"
    assert first.action.x == 10
    assert first.action.y == 20
    assert first.action.coordinate_space == "viewport"
    assert first.observation is not None
    assert first.observation.width == 1920
    assert first.post_state is not None
    assert first.post_state.observation is not None
    assert first.post_state.observation.image_path == "step_1_20260622@000001000000.png"
    assert second.action is not None
    assert second.action.type == "drag"
    assert second.action.x == 30
    assert second.action.y == 40


def test_osworld_adapter_preserves_multi_action_provenance(tmp_path: Path) -> None:
    path = write_minimal_osworld_dir(tmp_path)

    trace = OSWorldAdapter().load(path)

    first_post_state = trace.steps[0].post_state
    second_post_state = trace.steps[1].post_state
    assert first_post_state is not None
    assert second_post_state is not None
    assert first_post_state.state_metadata["source_model_step"] == "1"
    assert first_post_state.state_metadata["source_action_index"] == 0
    assert second_post_state.state_metadata["source_model_step"] == "1"
    assert second_post_state.state_metadata["source_action_index"] == 1
    assert trace.steps[0].observation is not None
    assert trace.steps[1].observation is not None
    assert trace.steps[0].observation.observation_id == "initial"
    assert trace.steps[1].observation.observation_id == "initial"


def test_osworld_adapter_does_not_fabricate_model_input(tmp_path: Path) -> None:
    path = write_minimal_osworld_dir(tmp_path)

    trace = OSWorldAdapter().load(path)

    assert all(step.model_input is None for step in trace.steps)


def test_osworld_adapter_handles_malformed_action_safely(tmp_path: Path) -> None:
    marker = tmp_path / "should_not_exist"
    rows = [
        {
            "step_num": 1,
            "action_timestamp": "20260622@000001000000",
            "action": f"__import__('pathlib').Path('{marker}').touch()",
            "response": "malformed",
            "screenshot_file": "step_1_20260622@000001000000.png",
        }
    ]
    write_png_header(tmp_path / "step_0_20260622@000000000000.png")
    write_png_header(tmp_path / "step_1_20260622@000001000000.png")
    path = tmp_path / "traj.jsonl"
    write_jsonl(path, rows)

    trace = OSWorldAdapter().load(path)

    assert not marker.exists()
    assert trace.steps[0].action is not None
    assert trace.steps[0].action.type == "unknown"
    assert trace.steps[0].action.x is None
    assert trace.steps[0].action.y is None


def test_osworld_adapter_rejects_invalid_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "traj.jsonl"
    path.write_text('{"step_num": 1}\nnot-json\n', encoding="utf-8")

    with pytest.raises(AdapterError, match="invalid JSONL"):
        OSWorldAdapter().load(path)


def test_osworld_real_public_case_triggers_current_checks() -> None:
    trace = OSWorldAdapter().load(REAL_OSWORLD)
    report = CheckEngine().run(trace)
    findings_by_rule = {}
    for finding in report.findings:
        findings_by_rule.setdefault(finding.rule_id, []).append(finding)

    assert report.status.value == "FAIL"
    assert "MMTRACE003" in findings_by_rule
    assert "MMTRACE005" in findings_by_rule

    coordinate_finding = findings_by_rule["MMTRACE003"][0]
    assert coordinate_finding.step_id == "17"
    assert coordinate_finding.evidence["x"] == 1493
    assert coordinate_finding.evidence["y"] == 1080
    assert coordinate_finding.evidence["frame_width"] == 1920
    assert coordinate_finding.evidence["frame_height"] == 1080
    assert trace.steps[16].action is not None
    assert trace.steps[16].action.target == "pyautogui.dragTo(1493, 1080, duration=0.5)"

    stale_findings = findings_by_rule["MMTRACE005"]
    assert len(stale_findings) >= 1
    assert stale_findings[0].evidence["used_observation_id"]
    assert stale_findings[0].evidence["newer_observation_id"]
    assert stale_findings[0].evidence["action_timestamp"]


def test_osworld_task_result_does_not_drive_report_status(tmp_path: Path) -> None:
    rows = [
        {
            "step_num": 1,
            "action_timestamp": "20260622@000001000000",
            "action": "pyautogui.scroll(-3)",
            "response": "scroll",
            "reward": 0,
            "done": False,
            "info": {},
            "screenshot_file": "step_1_20260622@000001000000.png",
        }
    ]
    write_png_header(tmp_path / "step_0_20260622@000000000000.png")
    write_png_header(tmp_path / "step_1_20260622@000001000000.png")
    (tmp_path / "result.txt").write_text("0.0\n", encoding="utf-8")
    path = tmp_path / "traj.jsonl"
    write_jsonl(path, rows)

    trace = OSWorldAdapter().load(path)
    report = CheckEngine().run(trace)

    assert trace.metadata["task_result"] == "0.0"
    assert report.status.value == "PASS"
    assert report.findings == []

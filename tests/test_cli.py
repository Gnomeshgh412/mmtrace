import json
from pathlib import Path

from mmtrace.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
REAL_OSWORLD = Path(__file__).parents[1] / "examples" / "osworld_real_failure" / "traj.jsonl"


def test_cli_valid_trace_exits_zero(capsys) -> None:
    exit_code = main(["check", str(FIXTURES / "valid_trace.json")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Status: PASS" in captured.out
    assert captured.err == ""


def test_cli_error_trace_exits_one(capsys) -> None:
    exit_code = main(["check", str(FIXTURES / "missing_observation.json")])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Status: FAIL" in captured.out
    assert "MMTRACE001" in captured.out


def test_cli_warning_only_exits_zero(tmp_path: Path, capsys) -> None:
    warning_trace = tmp_path / "warning_only.json"
    warning_trace.write_text(
        json.dumps(
            {
                "trace_id": "warning-only",
                "steps": [
                    {
                        "step_id": "step-001",
                        "observation": {"observation_id": "obs-001"},
                        "action": {"action_id": "action-001", "type": "click"},
                        "execution": {"status": "success"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["check", str(warning_trace)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Status: PASS" in captured.out
    assert "MMTRACE006" in captured.out


def test_cli_invalid_json_exits_two(tmp_path: Path, capsys) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text('{"trace_id": "broken",', encoding="utf-8")

    exit_code = main(["check", str(bad_json)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "MMTrace error:" in captured.err
    assert "invalid JSON" in captured.err


def test_cli_missing_file_exits_two(tmp_path: Path, capsys) -> None:
    exit_code = main(["check", str(tmp_path / "missing.json")])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "file not found" in captured.err


def test_cli_json_format_outputs_valid_json(capsys) -> None:
    exit_code = main(["check", str(FIXTURES / "coordinate_out_of_frame.json"), "--format", "json"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert exit_code == 1
    assert parsed["trace_id"] == "coordinate-out-of-frame"
    assert parsed["status"] == "FAIL"
    assert parsed["error_count"] == 1
    assert parsed["findings"][0]["rule_id"] == "MMTRACE003"


def test_cli_output_writes_report_file(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "report.json"

    exit_code = main(
        [
            "check",
            str(FIXTURES / "coordinate_out_of_frame.json"),
            "--format",
            "json",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    parsed = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert captured.out == ""
    assert parsed["status"] == "FAIL"
    assert parsed["findings"][0]["rule_id"] == "MMTRACE003"


def test_cli_rule_runs_only_selected_rule(capsys) -> None:
    exit_code = main(
        [
            "check",
            str(FIXTURES / "coordinate_out_of_frame.json"),
            "--rule",
            "MMTRACE003",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert exit_code == 1
    assert [finding["rule_id"] for finding in parsed["findings"]] == ["MMTRACE003"]


def test_cli_unknown_rule_exits_two(capsys) -> None:
    exit_code = main(["check", str(FIXTURES / "valid_trace.json"), "--rule", "MMTRACE999"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "unknown rule ID" in captured.err


def test_cli_osworld_adapter_reports_real_failure(capsys) -> None:
    exit_code = main(["check", str(REAL_OSWORLD), "--adapter", "osworld", "--format", "json"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    rule_ids = {finding["rule_id"] for finding in parsed["findings"]}
    assert exit_code == 1
    assert parsed["status"] == "FAIL"
    assert {"MMTRACE003", "MMTRACE005"} <= rule_ids

import json
import sys
from pathlib import Path

import pytest

from mmtrace.cli import main
from mmtrace import serve as serve_module

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
    assert parsed["error_count"] == 2
    assert {finding["rule_id"] for finding in parsed["findings"]} == {
        "MMTRACE003",
        "MMTRACE007",
    }


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


def test_cli_serve_help_lists_host_and_port(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["serve", "--help"])

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "serve" in captured.out
    assert "--host" in captured.out
    assert "127.0.0.1" in captured.out
    assert "--port" in captured.out
    assert "8000" in captured.out


def test_serve_missing_frontend_build_exits_two(tmp_path: Path, capsys) -> None:
    (tmp_path / "web" / "backend").mkdir(parents=True)
    (tmp_path / "web" / "frontend").mkdir(parents=True)

    exit_code = serve_module.serve(
        root=tmp_path,
        app_factory=lambda frontend_dist: pytest.fail(
            f"app should not be created for missing build: {frontend_dist}"
        ),
        run_server=lambda *args, **kwargs: pytest.fail("server should not start"),
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Frontend build not found." in captured.err
    assert "cd web/frontend" in captured.err
    assert "npm ci" in captured.err
    assert "npm run build" in captured.err
    assert "mmtrace serve" in captured.err
    assert "Traceback" not in captured.err


def test_serve_warns_for_public_host(tmp_path: Path, capsys) -> None:
    dist = tmp_path / "web" / "frontend" / "dist"
    (tmp_path / "web" / "backend").mkdir(parents=True)
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    started = {}

    exit_code = serve_module.serve(
        host="0.0.0.0",
        port=8123,
        root=tmp_path,
        app_factory=lambda frontend_dist: {"dist": frontend_dist},
        run_server=lambda app, **kwargs: started.update({"app": app, **kwargs}),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "MMTrace running at http://0.0.0.0:8123\n"
    assert "expose local traces and screenshots" in captured.err
    assert started == {
        "app": {"dist": dist},
        "host": "0.0.0.0",
        "port": 8123,
    }


def test_serve_adds_source_checkout_root_to_import_path(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "web" / "frontend" / "dist"
    (tmp_path / "web" / "backend").mkdir(parents=True)
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(sys, "path", [path for path in sys.path if path != str(tmp_path)])

    exit_code = serve_module.serve(
        root=tmp_path,
        app_factory=lambda frontend_dist: {"dist": frontend_dist},
        run_server=lambda *args, **kwargs: None,
    )

    assert exit_code == 0
    assert sys.path[0] == str(tmp_path)

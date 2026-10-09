import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import web.backend.app as backend_app
from web.backend.app import app

FIXTURES = Path(__file__).parent / "fixtures"
REAL_HISTORY = Path(__file__).parents[1] / "examples" / "browser_use_real" / "history.json"
REAL_OSWORLD = Path(__file__).parents[1] / "examples" / "osworld_real_failure" / "traj.jsonl"
REAL_HOLO4 = Path(__file__).parents[1] / "examples" / "holo4_real_execution_failure" / "trajectory.json"


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_mmtrace_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MMTRACE_HOME", str(tmp_path / "mmtrace-home"))


def post_analyze(path: Path, adapter: str):
    with path.open("rb") as trace_file:
        return client.post(
            "/api/analyze",
            data={"adapter": adapter},
            files={"trace_file": (path.name, trace_file, "application/json")},
        )


def post_analyze_with_artifacts(path: Path, adapter: str, artifacts: Path):
    with path.open("rb") as trace_file, artifacts.open("rb") as artifact_file:
        return client.post(
            "/api/analyze",
            data={"adapter": adapter},
            files={
                "trace_file": (path.name, trace_file, "application/json"),
                "artifacts": (artifacts.name, artifact_file, "application/zip"),
            },
        )


def write_trace_with_screenshots(path: Path, before: str, after: str | None = None) -> None:
    post_observation = (
        {
            "observation_id": "obs-after",
            "image_path": after,
            "width": 20,
            "height": 20,
            "viewport_width": 20,
            "viewport_height": 20,
        }
        if after is not None
        else None
    )
    payload = {
        "trace_id": "artifact-trace",
        "agent": "fixture-agent",
        "steps": [
            {
                "step_id": "step-001",
                "observation": {
                    "observation_id": "obs-before",
                    "image_path": before,
                    "width": 20,
                    "height": 20,
                    "viewport_width": 20,
                    "viewport_height": 20,
                },
                "action": {
                    "action_id": "action-001",
                    "type": "click",
                    "x": 5,
                    "y": 5,
                    "coordinate_space": "viewport",
                },
                "execution": {"status": "success"},
                "post_state": {
                    "observation": post_observation,
                    "state_metadata": {
                        "expected_coordinate_space": "viewport",
                    },
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def write_zip_symlink(path: Path, name: str) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, b"target")


def build_osworld_artifact_zip() -> Path:
    archive_path = Path(tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name)
    with zipfile.ZipFile(archive_path, "w") as archive:
        for screenshot in REAL_OSWORLD.parent.glob("*.png"):
            archive.write(screenshot, screenshot.name)
    return archive_path


def source_action_count(path: Path) -> int:
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


def test_health() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mmtrace"}


def test_analyze_generic_valid_trace() -> None:
    response = post_analyze(FIXTURES / "valid_trace.json", "generic")

    body = response.json()
    assert response.status_code == 200
    assert body["analysis_id"]
    assert body["trace"]["trace_id"] == "valid-trace"
    assert body["report"]["status"] == "PASS"
    assert body["report"]["error_count"] == 0
    assert [evaluation["rule_id"] for evaluation in body["evaluations"]] == [
        "MMTRACE001",
        "MMTRACE002",
        "MMTRACE003",
        "MMTRACE004",
        "MMTRACE005",
        "MMTRACE006",
        "MMTRACE007",
    ]
    assert body["artifacts"] == {"screenshots": {}}


def test_analyze_browser_use_real_history() -> None:
    response = post_analyze(REAL_HISTORY, "browser-use")

    body = response.json()
    evaluations = {evaluation["rule_id"]: evaluation for evaluation in body["evaluations"]}
    action_count = sum(1 for step in body["trace"]["steps"] if step["action"] is not None)
    assert response.status_code == 200
    assert body["report"]["status"] == "PASS"
    assert body["report"]["error_count"] == 0
    assert body["report"]["warning_count"] == 0
    assert action_count == source_action_count(REAL_HISTORY) == 4
    assert evaluations["MMTRACE001"]["coverage"] == "FULL"
    assert evaluations["MMTRACE001"]["outcome"] == "PASS"
    assert evaluations["MMTRACE002"]["coverage"] == "NOT_EVALUABLE"
    assert evaluations["MMTRACE003"]["coverage"] == "NOT_EVALUABLE"
    assert evaluations["MMTRACE004"]["coverage"] == "NOT_APPLICABLE"
    assert evaluations["MMTRACE005"]["coverage"] == "NOT_EVALUABLE"
    assert evaluations["MMTRACE006"]["coverage"] == "NOT_EVALUABLE"
    assert evaluations["MMTRACE007"]["coverage"] == "PARTIAL"
    assert evaluations["MMTRACE007"]["outcome"] == "PASS"


def test_analyze_osworld_real_failure() -> None:
    archive = build_osworld_artifact_zip()
    response = post_analyze_with_artifacts(REAL_OSWORLD, "osworld", archive)

    body = response.json()
    rule_ids = {finding["rule_id"] for finding in body["report"]["findings"]}
    evaluations = {evaluation["rule_id"]: evaluation for evaluation in body["evaluations"]}
    assert response.status_code == 200
    assert body["report"]["status"] == "FAIL"
    assert body["report"]["error_count"] == 1
    assert body["report"]["warning_count"] == 10
    assert {"MMTRACE003", "MMTRACE005"} <= rule_ids
    assert evaluations["MMTRACE003"]["coverage"] == "PARTIAL"
    assert evaluations["MMTRACE003"]["outcome"] == "ERROR"
    assert evaluations["MMTRACE003"]["finding_count"] == 1
    assert evaluations["MMTRACE005"]["coverage"] == "FULL"
    assert evaluations["MMTRACE005"]["outcome"] == "WARNING"
    assert evaluations["MMTRACE005"]["finding_count"] == 10
    archive.unlink()


def test_analyze_holo4_real_evaluations_and_reopen() -> None:
    analyze_response = post_analyze(REAL_HOLO4, "holo4")
    body = analyze_response.json()
    analysis_id = body["analysis_id"]
    evaluations = {evaluation["rule_id"]: evaluation for evaluation in body["evaluations"]}

    assert analyze_response.status_code == 200
    assert body["report"]["status"] == "FAIL"
    assert body["report"]["error_count"] == 5
    assert body["report"]["warning_count"] == 0
    assert len(body["evaluations"]) == 7
    assert evaluations["MMTRACE007"]["coverage"] == "PARTIAL"
    assert evaluations["MMTRACE007"]["outcome"] == "ERROR"
    assert evaluations["MMTRACE007"]["applicable_units"] == 100
    assert evaluations["MMTRACE007"]["evaluable_units"] == 25
    assert evaluations["MMTRACE007"]["not_evaluable_units"] == 75
    assert evaluations["MMTRACE007"]["finding_count"] == 5
    missing = evaluations["MMTRACE007"]["missing_evidence"]
    assert len(missing) == 1
    assert missing[0]["code"] == "execution.status"
    assert missing[0]["count"] == 75
    assert len(missing[0]["step_ids"]) == 75

    reopened = client.get(f"/api/analyses/{analysis_id}")

    assert reopened.status_code == 200
    assert reopened.json()["evaluations"] == body["evaluations"]


def test_analyze_holo4_trace(tmp_path: Path) -> None:
    trace = tmp_path / "holo4.json"
    trace.write_text(
        json.dumps(
            {
                "id": "holo4-web-fixture",
                "model": "Holo4 27B",
                "benchmark": "AutomationBench",
                "instruction": "Fetch a missing spreadsheet.",
                "steps": [
                    {
                        "calls": [
                            {
                                "name": "api_fetch",
                                "args": {
                                    "method": "GET",
                                    "url": "https://sheets.googleapis.com/v4/spreadsheets/missing",
                                },
                            }
                        ],
                        "results": ['{"error": "Spreadsheet not found"}'],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    response = post_analyze(trace, "holo4")
    body = response.json()

    assert response.status_code == 200
    assert body["trace"]["metadata"]["source"] == "holo4"
    assert body["report"]["status"] == "FAIL"
    assert body["report"]["findings"][0]["rule_id"] == "MMTRACE007"


def test_analyze_without_artifact_zip_keeps_empty_artifacts() -> None:
    response = post_analyze(FIXTURES / "valid_trace.json", "generic")

    assert response.status_code == 200
    assert response.json()["artifacts"] == {"screenshots": {}}


def test_analyze_with_valid_screenshot_zip_maps_observations(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    write_trace_with_screenshots(
        trace,
        before="screenshots/before.png",
        after="screenshots/after.png",
    )
    write_zip(
        archive,
        {
            "screenshots/before.png": b"before-png",
            "screenshots/after.png": b"after-png",
        },
    )

    response = post_analyze_with_artifacts(trace, "generic", archive)

    screenshots = response.json()["artifacts"]["screenshots"]
    assert response.status_code == 200
    assert set(screenshots) == {"obs-before", "obs-after"}
    assert screenshots["obs-before"].startswith(
        f"/api/artifacts/{response.json()['analysis_id']}/"
    )


def test_list_analyses_does_not_include_evaluations() -> None:
    response = post_analyze(FIXTURES / "valid_trace.json", "generic")
    summaries = client.get("/api/analyses").json()

    assert response.status_code == 200
    assert summaries
    assert "evaluations" not in summaries[0]


def test_get_detail_reads_frozen_evaluations_without_rerunning_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyze_response = post_analyze(FIXTURES / "coordinate_out_of_frame.json", "generic")
    body = analyze_response.json()
    analysis_id = body["analysis_id"]

    def forbidden_evaluate(*args, **kwargs):
        raise AssertionError("EvaluationEngine must not run during GET detail")

    monkeypatch.setattr(backend_app.EvaluationEngine, "evaluate", forbidden_evaluate)

    detail_response = client.get(f"/api/analyses/{analysis_id}")

    assert detail_response.status_code == 200
    assert detail_response.json()["evaluations"] == body["evaluations"]


def test_corrupt_new_evaluation_snapshot_returns_sanitized_500(tmp_path: Path) -> None:
    analyze_response = post_analyze(FIXTURES / "valid_trace.json", "generic")
    analysis_id = analyze_response.json()["analysis_id"]
    evaluation_path = (
        tmp_path
        / "mmtrace-home"
        / "analyses"
        / analysis_id
        / "evaluation"
        / "evaluations.json"
    )
    evaluation_path.unlink()

    client_without_server_exceptions = TestClient(app, raise_server_exceptions=False)
    response = client_without_server_exceptions.get(f"/api/analyses/{analysis_id}")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_evaluation_failure_does_not_persist_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_evaluate(*args, **kwargs):
        raise RuntimeError("evaluation failed")

    monkeypatch.setattr(backend_app.EvaluationEngine, "evaluate", broken_evaluate)
    client_without_server_exceptions = TestClient(app, raise_server_exceptions=False)

    response = post_analyze_with_client(
        client_without_server_exceptions,
        FIXTURES / "valid_trace.json",
        "generic",
    )

    assert response.status_code == 500
    home = tmp_path / "mmtrace-home"
    db_path = home / "mmtrace.db"
    if db_path.exists():
        with sqlite3.connect(db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0
    assert not list((home / "analyses").glob("*")) if (home / "analyses").exists() else True


def test_get_mapped_artifact_returns_image_content_type(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    write_trace_with_screenshots(trace, before="screenshots/before.png")
    write_zip(archive, {"screenshots/before.png": b"png-content"})

    analyze_response = post_analyze_with_artifacts(trace, "generic", archive)
    artifact_url = analyze_response.json()["artifacts"]["screenshots"]["obs-before"]

    response = client.get(artifact_url)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"png-content"


def test_get_unknown_analysis_artifact_returns_404() -> None:
    response = client.get("/api/artifacts/unknown/screenshots/before.png")

    assert response.status_code == 404


def test_get_unknown_artifact_returns_404(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    write_trace_with_screenshots(trace, before="screenshots/before.png")
    write_zip(archive, {"screenshots/before.png": b"png-content"})
    analyze_response = post_analyze_with_artifacts(trace, "generic", archive)
    analysis_id = analyze_response.json()["analysis_id"]

    response = client.get(f"/api/artifacts/{analysis_id}/screenshots/missing.png")

    assert response.status_code == 404


def test_artifact_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    write_trace_with_screenshots(trace, before="escape.png")
    write_zip(archive, {"../escape.png": b"bad"})

    response = post_analyze_with_artifacts(trace, "generic", archive)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_artifact_zip_absolute_path_is_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    write_trace_with_screenshots(trace, before="escape.png")
    write_zip(archive, {"/escape.png": b"bad"})

    response = post_analyze_with_artifacts(trace, "generic", archive)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_artifact_zip_symlink_is_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    write_trace_with_screenshots(trace, before="screenshots/link.png")
    write_zip_symlink(archive, "screenshots/link.png")

    response = post_analyze_with_artifacts(trace, "generic", archive)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_ambiguous_screenshot_basename_is_not_mapped(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    write_trace_with_screenshots(trace, before="/runtime/screenshots/step.png")
    write_zip(
        archive,
        {
            "first/step.png": b"first",
            "second/step.png": b"second",
        },
    )

    response = post_analyze_with_artifacts(trace, "generic", archive)

    assert response.status_code == 200
    assert response.json()["artifacts"]["screenshots"] == {}


def test_analyze_unknown_adapter() -> None:
    response = post_analyze(FIXTURES / "valid_trace.json", "unknown")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_ADAPTER"


def test_analyze_invalid_json(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"trace_id": "broken",', encoding="utf-8")

    response = post_analyze(invalid, "generic")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_analyze_schema_invalid(tmp_path: Path) -> None:
    invalid = tmp_path / "schema_invalid.json"
    invalid.write_text('{"trace_id": "broken", "steps": "invalid"}', encoding="utf-8")

    response = post_analyze(invalid, "generic")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TRACE"


def test_internal_error_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_engine() -> backend_app.CheckEngine:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(backend_app, "CheckEngine", broken_engine)
    client_without_server_exceptions = TestClient(app, raise_server_exceptions=False)

    response = post_analyze_with_client(
        client_without_server_exceptions,
        FIXTURES / "valid_trace.json",
        "generic",
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def post_analyze_with_client(test_client: TestClient, path: Path, adapter: str):
    with path.open("rb") as trace_file:
        return test_client.post(
            "/api/analyze",
            data={"adapter": adapter},
            files={"trace_file": (path.name, trace_file, "application/json")},
        )

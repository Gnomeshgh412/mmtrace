import json
import shutil
import sqlite3
import zipfile
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mmtrace.adapters.generic_json import GenericJSONAdapter
from mmtrace.engine import CheckEngine
from mmtrace.evaluation import EvaluationEngine
from mmtrace.schema.finding import Finding, Report, Severity
from web.backend.app import app
from web.backend.persistence import ArtifactInput, PersistenceError, PersistenceStore, SnapshotInput
from web.backend.persistence.db import SCHEMA_VERSION, connect
from web.backend.persistence.store import (
    EVALUATION_RELPATH,
    EVALUATION_SNAPSHOT_FORMAT,
    EVALUATION_SNAPSHOT_VERSION,
    RULE_EVALUATIONS_FEATURE,
    SNAPSHOT_FORMAT,
    SNAPSHOT_MANIFEST,
)

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parents[1] / "examples"
HOLO4_TRACE = EXAMPLES / "holo4_real_execution_failure" / "trajectory.json"
HOLO4_SCREENSHOTS = EXAMPLES / "holo4_real_execution_failure" / "screenshots"
BROWSER_USE_HISTORY = EXAMPLES / "browser_use_real" / "history.json"
OSWORLD_TRACE = EXAMPLES / "osworld_real_failure" / "traj.jsonl"


@pytest.fixture(autouse=True)
def isolated_mmtrace_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "mmtrace-home"
    monkeypatch.setenv("MMTRACE_HOME", str(home))
    return home


def post_analyze(client: TestClient, path: Path, adapter: str):
    with path.open("rb") as trace_file:
        return client.post(
            "/api/analyze",
            data={"adapter": adapter},
            files={"trace_file": (path.name, trace_file, "application/json")},
        )


def post_analyze_with_artifacts(client: TestClient, path: Path, adapter: str, archive: Path):
    with path.open("rb") as trace_file, archive.open("rb") as artifact_file:
        return client.post(
            "/api/analyze",
            data={"adapter": adapter},
            files={
                "trace_file": (path.name, trace_file, "application/json"),
                "artifacts": (archive.name, artifact_file, "application/zip"),
            },
        )


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


def make_holo4_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for screenshot in HOLO4_SCREENSHOTS.glob("*.webp"):
            archive.write(screenshot, f"screenshots/{screenshot.name}")
    return path


def make_osworld_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for screenshot in OSWORLD_TRACE.parent.glob("*.png"):
            archive.write(screenshot, screenshot.name)
    return path


def snapshot_input(tmp_path: Path, source: Path | None = None) -> SnapshotInput:
    source_path = source or FIXTURES / "valid_trace.json"
    trace = GenericJSONAdapter().load(source_path)
    report = CheckEngine().run(trace)
    evaluations = EvaluationEngine().evaluate(trace, report.findings)
    return SnapshotInput(
        analysis_id="11111111-1111-4111-8111-111111111111",
        adapter="generic",
        source_path=source_path,
        source_filename=source_path.name,
        trace=trace,
        report=report,
        evaluations=evaluations,
    )


def snapshot_with_id(tmp_path: Path, analysis_id: str) -> SnapshotInput:
    return snapshot_input(tmp_path).model_copy(update={"analysis_id": analysis_id})


def write_snapshot_manifest(path: Path, analysis_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "format": SNAPSHOT_FORMAT,
                "analysis_id": analysis_id,
                "schema_version": SCHEMA_VERSION,
            }
        ),
        encoding="utf-8",
    )


def write_snapshot_manifest_with_features(
    path: Path,
    analysis_id: str,
    features: list[str],
) -> None:
    path.write_text(
        json.dumps(
            {
                "format": SNAPSHOT_FORMAT,
                "analysis_id": analysis_id,
                "schema_version": SCHEMA_VERSION,
                "features": features,
            }
        ),
        encoding="utf-8",
    )


def make_finalized_snapshot(root: Path, analysis_id: str) -> Path:
    analysis_dir = root / "analyses" / analysis_id
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "source").mkdir()
    (analysis_dir / "normalized").mkdir()
    (analysis_dir / "report").mkdir()
    write_snapshot_manifest(analysis_dir / SNAPSHOT_MANIFEST, analysis_id)
    return analysis_dir


def test_schema_initializes_fresh_db_and_keeps_v1(isolated_mmtrace_home: Path) -> None:
    store = PersistenceStore(isolated_mmtrace_home)

    with connect(store.db_path) as connection:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    with connect(store.db_path) as connection:
        second_user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert user_version == second_user_version == 1
    assert {"analyses", "findings", "artifacts"} <= tables
    assert {
        "idx_analyses_analyzed_at",
        "idx_analyses_status",
        "idx_analyses_adapter",
        "idx_findings_analysis_id",
        "idx_findings_rule_id",
        "idx_findings_severity",
        "idx_artifacts_analysis_id",
        "idx_artifacts_analysis_observation",
    } <= indexes


def test_newer_schema_version_is_rejected(isolated_mmtrace_home: Path) -> None:
    isolated_mmtrace_home.mkdir()
    db_path = isolated_mmtrace_home / "mmtrace.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA user_version = 999")

    with pytest.raises(PersistenceError):
        PersistenceStore(isolated_mmtrace_home).list_analyses()


def test_analyze_list_filters_and_reopen(isolated_mmtrace_home: Path) -> None:
    client = TestClient(app)
    pass_response = post_analyze(client, FIXTURES / "valid_trace.json", "generic")
    fail_response = post_analyze(client, FIXTURES / "coordinate_out_of_frame.json", "generic")

    assert pass_response.status_code == 200
    assert fail_response.status_code == 200
    pass_id = pass_response.json()["analysis_id"]
    fail_id = fail_response.json()["analysis_id"]
    assert pass_id != fail_id

    all_summaries = client.get("/api/analyses").json()
    fail_summaries = client.get("/api/analyses", params={"status": "FAIL"}).json()
    error_summaries = client.get("/api/analyses", params={"findings": "errors"}).json()
    none_summaries = client.get("/api/analyses", params={"findings": "none"}).json()
    search_summaries = client.get("/api/analyses", params={"search": "coordinate"}).json()

    assert [summary["analysis_id"] for summary in all_summaries] == [fail_id, pass_id]
    assert [summary["analysis_id"] for summary in fail_summaries] == [fail_id]
    assert [summary["analysis_id"] for summary in error_summaries] == [fail_id]
    assert [summary["analysis_id"] for summary in none_summaries] == [pass_id]
    assert [summary["analysis_id"] for summary in search_summaries] == [fail_id]
    assert {hit["rule_id"] for hit in fail_summaries[0]["rule_hits"]} == {
        "MMTRACE003",
        "MMTRACE007",
    }

    reopened = client.get(f"/api/analyses/{fail_id}")
    assert reopened.status_code == 200
    assert reopened.json()["analysis_id"] == fail_id
    assert reopened.json()["report"]["status"] == "FAIL"


def test_reopen_after_backend_restart_keeps_artifact_access(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    trace.write_text(
        json.dumps(
            {
                "trace_id": "restart-artifact",
                "steps": [
                    {
                        "step_id": "step-1",
                        "observation": {
                            "observation_id": "obs-before",
                            "image_path": "screenshots/before.png",
                            "width": 20,
                            "height": 20,
                            "viewport_width": 20,
                            "viewport_height": 20,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    make_zip(archive, {"screenshots/before.png": b"png-content"})

    first_client = TestClient(app)
    analyze_response = post_analyze_with_artifacts(first_client, trace, "generic", archive)
    body = analyze_response.json()
    analysis_id = body["analysis_id"]
    artifact_url = body["artifacts"]["screenshots"]["obs-before"]

    restarted_client = TestClient(app)
    detail_response = restarted_client.get(f"/api/analyses/{analysis_id}")
    artifact_response = restarted_client.get(artifact_url)

    assert detail_response.status_code == 200
    assert detail_response.json()["artifacts"]["screenshots"]["obs-before"] == artifact_url
    assert detail_response.json()["evaluations"] == body["evaluations"]
    assert artifact_response.status_code == 200
    assert artifact_response.content == b"png-content"


def test_new_snapshot_persists_rule_evaluations_and_marker_feature(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)

    detail = PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)
    analysis_dir = isolated_mmtrace_home / "analyses" / snapshot.analysis_id
    manifest = json.loads((analysis_dir / SNAPSHOT_MANIFEST).read_text(encoding="utf-8"))
    evaluation_payload = json.loads(
        (analysis_dir / EVALUATION_RELPATH).read_text(encoding="utf-8")
    )

    assert manifest["features"] == [RULE_EVALUATIONS_FEATURE]
    assert evaluation_payload["format"] == EVALUATION_SNAPSHOT_FORMAT
    assert evaluation_payload["schema_version"] == EVALUATION_SNAPSHOT_VERSION
    assert [evaluation.rule_id for evaluation in detail.evaluations] == [
        "MMTRACE001",
        "MMTRACE002",
        "MMTRACE003",
        "MMTRACE004",
        "MMTRACE005",
        "MMTRACE006",
        "MMTRACE007",
    ]
    assert detail.model_dump(mode="json")["evaluations"] == [
        evaluation.model_dump(mode="json") for evaluation in snapshot.evaluations
    ]


def test_legacy_snapshot_without_evaluations_reopens_with_null(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)
    store = PersistenceStore(isolated_mmtrace_home)
    detail = store.persist_analysis(snapshot)
    analysis_dir = isolated_mmtrace_home / "analyses" / snapshot.analysis_id
    shutil.rmtree(analysis_dir / "evaluation")
    write_snapshot_manifest(analysis_dir / SNAPSHOT_MANIFEST, snapshot.analysis_id)

    reopened = PersistenceStore(isolated_mmtrace_home).get_analysis(snapshot.analysis_id)

    assert detail.evaluations is not None
    assert reopened.evaluations is None
    assert reopened.trace["trace_id"] == snapshot.trace.trace_id
    assert reopened.report["status"] == snapshot.report.status.value


def test_legacy_snapshot_detail_api_returns_null_evaluations(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)
    PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)
    analysis_dir = isolated_mmtrace_home / "analyses" / snapshot.analysis_id
    shutil.rmtree(analysis_dir / "evaluation")
    write_snapshot_manifest(analysis_dir / SNAPSHOT_MANIFEST, snapshot.analysis_id)

    response = TestClient(app).get(f"/api/analyses/{snapshot.analysis_id}")

    assert response.status_code == 200
    assert response.json()["evaluations"] is None


def test_features_empty_is_legacy_compatible(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)
    PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)
    analysis_dir = isolated_mmtrace_home / "analyses" / snapshot.analysis_id
    shutil.rmtree(analysis_dir / "evaluation")
    write_snapshot_manifest_with_features(analysis_dir / SNAPSHOT_MANIFEST, snapshot.analysis_id, [])

    assert PersistenceStore(isolated_mmtrace_home).get_analysis(snapshot.analysis_id).evaluations is None


def test_unknown_snapshot_feature_is_ignored(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)
    PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)
    analysis_dir = isolated_mmtrace_home / "analyses" / snapshot.analysis_id
    write_snapshot_manifest_with_features(
        analysis_dir / SNAPSHOT_MANIFEST,
        snapshot.analysis_id,
        [RULE_EVALUATIONS_FEATURE, "future_optional_feature"],
    )

    assert PersistenceStore(isolated_mmtrace_home).get_analysis(snapshot.analysis_id).evaluations


def test_malformed_snapshot_features_are_rejected(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)
    PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)
    analysis_dir = isolated_mmtrace_home / "analyses" / snapshot.analysis_id
    (analysis_dir / SNAPSHOT_MANIFEST).write_text(
        json.dumps(
            {
                "format": SNAPSHOT_FORMAT,
                "analysis_id": snapshot.analysis_id,
                "schema_version": SCHEMA_VERSION,
                "features": "rule_evaluations",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PersistenceError):
        PersistenceStore(isolated_mmtrace_home).get_analysis(snapshot.analysis_id)


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (lambda path: path.unlink(), "invalid MMTrace evaluation snapshot"),
        (lambda path: path.write_text("{not-json", encoding="utf-8"), "invalid MMTrace evaluation snapshot"),
        (
            lambda path: path.write_text(
                json.dumps({"format": "wrong", "schema_version": 1, "evaluations": []}),
                encoding="utf-8",
            ),
            "invalid MMTrace evaluation snapshot format",
        ),
        (
            lambda path: path.write_text(
                json.dumps(
                    {
                        "format": EVALUATION_SNAPSHOT_FORMAT,
                        "schema_version": 999,
                        "evaluations": [],
                    }
                ),
                encoding="utf-8",
            ),
            "unsupported MMTrace evaluation snapshot schema version",
        ),
        (
            lambda path: path.write_text(
                json.dumps(
                    {
                        "format": EVALUATION_SNAPSHOT_FORMAT,
                        "schema_version": EVALUATION_SNAPSHOT_VERSION,
                        "evaluations": [{"rule_id": "MMTRACE001"}],
                    }
                ),
                encoding="utf-8",
            ),
            "invalid MMTrace evaluation snapshot",
        ),
    ],
)
def test_new_snapshot_evaluation_corruption_is_not_legacy(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    mutate,
    expected_message: str,
) -> None:
    snapshot = snapshot_input(tmp_path)
    PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)
    evaluation_path = isolated_mmtrace_home / "analyses" / snapshot.analysis_id / EVALUATION_RELPATH
    mutate(evaluation_path)

    with pytest.raises(PersistenceError, match=expected_message):
        PersistenceStore(isolated_mmtrace_home).get_analysis(snapshot.analysis_id)

    with connect(isolated_mmtrace_home / "mmtrace.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1


def test_reopen_reads_frozen_evaluations_without_running_engine(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = snapshot_input(tmp_path)
    persisted = PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)
    frozen = persisted.model_dump(mode="json")["evaluations"]

    def forbidden_evaluate(*args, **kwargs):
        raise AssertionError("EvaluationEngine must not run during reopen")

    monkeypatch.setattr("mmtrace.evaluation.engine.EvaluationEngine.evaluate", forbidden_evaluate)

    reopened = PersistenceStore(isolated_mmtrace_home).get_analysis(snapshot.analysis_id)

    assert reopened.model_dump(mode="json")["evaluations"] == frozen


def test_artifact_route_rejects_escape_and_injection(tmp_path: Path) -> None:
    client = TestClient(app)
    trace = tmp_path / "trace.json"
    archive = tmp_path / "screenshots.zip"
    trace.write_text(
        json.dumps(
            {
                "trace_id": "artifact-security",
                "steps": [
                    {
                        "step_id": "step-1",
                        "observation": {
                            "observation_id": "obs-before",
                            "image_path": "before.png",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    make_zip(archive, {"before.png": b"png-content"})
    analysis_id = post_analyze_with_artifacts(client, trace, "generic", archive).json()[
        "analysis_id"
    ]

    assert client.get(f"/api/artifacts/{analysis_id}/../mmtrace.db").status_code == 404
    assert client.get(f"/api/artifacts/{analysis_id}//tmp/escape.png").status_code == 404
    assert client.get("/api/analyses/not-a-uuid").status_code == 404
    assert (
        client.get("/api/analyses/11111111-1111-4111-8111-111111111111' OR '1'='1")
        .status_code
        == 404
    )


def test_persistence_failure_leaves_no_row_or_final_directory(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = PersistenceStore(isolated_mmtrace_home)

    def broken_insert(connection, metadata):
        raise sqlite3.DatabaseError("insert failed")

    monkeypatch.setattr(store, "_insert_rows", broken_insert)

    with pytest.raises(sqlite3.DatabaseError):
        store.persist_analysis(snapshot_input(tmp_path))

    with connect(store.db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 0
    assert not (isolated_mmtrace_home / "analyses" / snapshot_input(tmp_path).analysis_id).exists()


def test_source_write_failure_leaves_no_row_or_snapshot_workspace(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = snapshot_input(tmp_path)
    original_copyfile = __import__("shutil").copyfile

    def fail_source_copy(src, dst, *args, **kwargs):
        if Path(dst).parent.name == "source":
            raise OSError("source copy failed")
        return original_copyfile(src, dst, *args, **kwargs)

    monkeypatch.setattr("web.backend.persistence.store.shutil.copyfile", fail_source_copy)

    with pytest.raises(OSError):
        PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)

    with connect(PersistenceStore(isolated_mmtrace_home).db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 0
    assert not (isolated_mmtrace_home / "analyses" / snapshot.analysis_id).exists()
    assert not list(isolated_mmtrace_home.glob(f".{snapshot.analysis_id}-*"))


@pytest.mark.parametrize(
    ("directory_name", "error_message"),
        [
            ("normalized", "normalized write failed"),
            ("report", "report write failed"),
            ("evaluation", "evaluation write failed"),
        ],
    )
def test_snapshot_json_write_failure_leaves_no_row_or_snapshot_workspace(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory_name: str,
    error_message: str,
) -> None:
    snapshot = snapshot_input(tmp_path)
    original_write_text = Path.write_text

    def fail_snapshot_write(self: Path, data: str, *args, **kwargs):
        if self.parent.name == directory_name:
            raise OSError(error_message)
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_snapshot_write)

    with pytest.raises(OSError):
        PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)

    with connect(PersistenceStore(isolated_mmtrace_home).db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 0
    assert not (isolated_mmtrace_home / "analyses" / snapshot.analysis_id).exists()
    assert not list(isolated_mmtrace_home.glob(f".{snapshot.analysis_id}-*"))


def test_artifact_copy_failure_leaves_no_row_or_final_directory(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "trace.json"
    source.write_text((FIXTURES / "valid_trace.json").read_text(encoding="utf-8"), encoding="utf-8")
    artifact = tmp_path / "before.png"
    artifact.write_bytes(b"png-content")
    snapshot = snapshot_input(tmp_path, source)
    snapshot.artifacts.append(
        ArtifactInput(
            observation_id="obs-before",
            kind="screenshot",
            source_path="before.png",
            temp_path=artifact,
            stored_name="obs-before.png",
        )
    )

    original_copyfile = __import__("shutil").copyfile

    def fail_artifact_copy(src, dst, *args, **kwargs):
        if Path(dst).parent.name == "artifacts":
            raise OSError("copy failed")
        return original_copyfile(src, dst, *args, **kwargs)

    monkeypatch.setattr("web.backend.persistence.store.shutil.copyfile", fail_artifact_copy)

    with pytest.raises(OSError):
        PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)

    with connect(PersistenceStore(isolated_mmtrace_home).db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 0
    assert not (isolated_mmtrace_home / "analyses" / snapshot.analysis_id).exists()


def test_os_replace_failure_rolls_back_and_cleans_temp_snapshot(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = snapshot_input(tmp_path)
    store = PersistenceStore(isolated_mmtrace_home)

    def fail_publish(temp_dir: Path, final_dir: Path) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr(store, "_publish_snapshot", fail_publish)

    with pytest.raises(OSError):
        store.persist_analysis(snapshot)

    with connect(store.db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 0
    assert not (isolated_mmtrace_home / "analyses" / snapshot.analysis_id).exists()
    assert not list(isolated_mmtrace_home.glob(f".{snapshot.analysis_id}-*"))


def test_commit_failure_removes_finalized_snapshot_and_rolls_back_row(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = snapshot_input(tmp_path)
    store = PersistenceStore(isolated_mmtrace_home)

    def fail_commit(connection) -> None:
        raise sqlite3.DatabaseError("commit failed")

    monkeypatch.setattr(store, "_commit", fail_commit)

    with pytest.raises(sqlite3.DatabaseError):
        store.persist_analysis(snapshot)

    with connect(store.db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 0
    assert not (isolated_mmtrace_home / "analyses" / snapshot.analysis_id).exists()


def test_startup_reconciliation_removes_crash_after_finalize_orphan(
    isolated_mmtrace_home: Path,
) -> None:
    analysis_id = str(uuid4())
    orphan = make_finalized_snapshot(isolated_mmtrace_home, analysis_id)

    assert orphan.exists()

    PersistenceStore(isolated_mmtrace_home)

    assert not orphan.exists()
    with connect(isolated_mmtrace_home / "mmtrace.db") as connection:
        count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 0


def test_startup_reconciliation_preserves_committed_snapshot(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)
    store = PersistenceStore(isolated_mmtrace_home)
    store.persist_analysis(snapshot)
    final_dir = isolated_mmtrace_home / "analyses" / snapshot.analysis_id

    PersistenceStore(isolated_mmtrace_home)

    assert final_dir.is_dir()
    assert (
        PersistenceStore(isolated_mmtrace_home)
        .get_analysis(snapshot.analysis_id)
        .analysis_id
        == snapshot.analysis_id
    )


def test_missing_committed_snapshot_is_reported_as_corruption(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)
    store = PersistenceStore(isolated_mmtrace_home)
    store.persist_analysis(snapshot)
    shutil.rmtree(isolated_mmtrace_home / "analyses" / snapshot.analysis_id)

    with pytest.raises(PersistenceError):
        PersistenceStore(isolated_mmtrace_home).get_analysis(snapshot.analysis_id)

    with connect(isolated_mmtrace_home / "mmtrace.db") as connection:
        count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert count == 1


def test_startup_reconciliation_preserves_unknown_directories_and_symlinks(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    analyses_root = isolated_mmtrace_home / "analyses"
    analyses_root.mkdir(parents=True)
    random_dir = analyses_root / "random-folder"
    random_dir.mkdir()
    uuid_without_marker = analyses_root / str(uuid4())
    uuid_without_marker.mkdir()
    mismatched_id = str(uuid4())
    mismatched_dir = analyses_root / str(uuid4())
    mismatched_dir.mkdir()
    write_snapshot_manifest(mismatched_dir / SNAPSHOT_MANIFEST, mismatched_id)

    target = tmp_path / "do-not-delete"
    target.mkdir()
    symlink = analyses_root / str(uuid4())
    symlink.symlink_to(target, target_is_directory=True)

    PersistenceStore(isolated_mmtrace_home)

    assert random_dir.is_dir()
    assert uuid_without_marker.is_dir()
    assert mismatched_dir.is_dir()
    assert symlink.is_symlink()
    assert target.is_dir()


def test_same_timestamp_ordering_is_deterministic(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "web.backend.persistence.store._utc_now_iso",
        lambda: "2026-10-09T07:42:31.123456Z",
    )
    lower_id = "11111111-1111-4111-8111-111111111111"
    higher_id = "22222222-2222-4222-8222-222222222222"
    store = PersistenceStore(isolated_mmtrace_home)

    store.persist_analysis(snapshot_with_id(tmp_path, lower_id))
    store.persist_analysis(snapshot_with_id(tmp_path, higher_id))

    assert [summary.analysis_id for summary in store.list_analyses()] == [
        higher_id,
        lower_id,
    ]


def test_warning_only_pass_analysis_filters_are_distinct(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)
    report = Report.from_findings(
        trace_id=snapshot.trace.trace_id or "",
        findings=[
            Finding(
                rule_id="MMTRACE006",
                severity=Severity.WARNING,
                step_id="step-001",
                title="Missing Post-Action Verification",
            )
        ],
    )
    snapshot = snapshot.model_copy(
        update={
            "analysis_id": str(uuid4()),
            "report": report,
            "evaluations": EvaluationEngine().evaluate(snapshot.trace, report.findings),
        }
    )
    store = PersistenceStore(isolated_mmtrace_home)

    store.persist_analysis(snapshot)

    assert [summary.analysis_id for summary in store.list_analyses(status="PASS")] == [
        snapshot.analysis_id
    ]
    assert [summary.analysis_id for summary in store.list_analyses(findings="warnings")] == [
        snapshot.analysis_id
    ]
    assert store.list_analyses(findings="none") == []


def test_persisted_version_uses_package_metadata(
    isolated_mmtrace_home: Path,
    tmp_path: Path,
) -> None:
    snapshot = snapshot_input(tmp_path)

    PersistenceStore(isolated_mmtrace_home).persist_analysis(snapshot)

    with connect(isolated_mmtrace_home / "mmtrace.db") as connection:
        mmtrace_version = connection.execute(
            "SELECT mmtrace_version FROM analyses WHERE analysis_id = ?",
            (snapshot.analysis_id,),
        ).fetchone()[0]
    assert mmtrace_version == version("mmtrace")


def test_real_holo4_persistence_e2e(isolated_mmtrace_home: Path, tmp_path: Path) -> None:
    archive = make_holo4_zip(tmp_path / "holo4-screenshots.zip")
    client = TestClient(app)

    analyze_response = post_analyze_with_artifacts(client, HOLO4_TRACE, "holo4", archive)
    body = analyze_response.json()
    analysis_id = body["analysis_id"]

    assert analyze_response.status_code == 200
    assert body["report"]["status"] == "FAIL"
    assert body["report"]["error_count"] == 5
    assert body["report"]["warning_count"] == 0
    assert sum(1 for finding in body["report"]["findings"] if finding["rule_id"] == "MMTRACE007") == 5
    assert body["artifacts"]["screenshots"]

    with sqlite3.connect(isolated_mmtrace_home / "mmtrace.db") as connection:
        analysis_count = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        finding_count = connection.execute(
            "SELECT COUNT(*) FROM findings WHERE rule_id = 'MMTRACE007'"
        ).fetchone()[0]
        artifact_count = connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        model, benchmark = connection.execute(
            "SELECT model, benchmark FROM analyses WHERE analysis_id = ?",
            (analysis_id,),
        ).fetchone()

    assert analysis_count == 1
    assert finding_count == 5
    assert artifact_count > 0
    assert model == "Holo4 27B"
    assert benchmark == "OSWorld"

    reopened = TestClient(app).get(f"/api/analyses/{analysis_id}")
    artifact_url = next(iter(reopened.json()["artifacts"]["screenshots"].values()))
    assert reopened.status_code == 200
    assert reopened.json()["report"]["status"] == "FAIL"
    assert TestClient(app).get(artifact_url).status_code == 200


def test_browser_use_and_osworld_regressions_persist(tmp_path: Path) -> None:
    client = TestClient(app)
    browser_response = post_analyze(client, BROWSER_USE_HISTORY, "browser-use")
    osworld_response = post_analyze_with_artifacts(
        client,
        OSWORLD_TRACE,
        "osworld",
        make_osworld_zip(tmp_path / "osworld-screenshots.zip"),
    )

    assert browser_response.status_code == 200
    assert browser_response.json()["report"]["status"] == "PASS"
    assert browser_response.json()["report"]["error_count"] == 0
    assert browser_response.json()["report"]["warning_count"] == 0

    osworld_report = osworld_response.json()["report"]
    assert osworld_response.status_code == 200
    assert osworld_report["status"] == "FAIL"
    assert osworld_report["error_count"] == 1
    assert osworld_report["warning_count"] == 10
    assert {"MMTRACE003", "MMTRACE005"} <= {
        finding["rule_id"] for finding in osworld_report["findings"]
    }

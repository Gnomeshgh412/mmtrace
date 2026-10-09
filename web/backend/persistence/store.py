"""Local-first immutable analysis snapshot store."""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import posixpath
import shutil
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from mmtrace.schema.finding import Severity

from web.backend.persistence.db import SCHEMA_VERSION, PersistenceError, connect
from web.backend.persistence.models import (
    AnalysisDetail,
    AnalysisSummary,
    ArtifactInput,
    RuleHit,
    SnapshotInput,
)

SNAPSHOT_MANIFEST = ".mmtrace-snapshot.json"
SNAPSHOT_FORMAT = "mmtrace-analysis-snapshot"

logger = logging.getLogger(__name__)


class PersistenceStore:
    """Persist and load immutable local analysis snapshots."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or mmtrace_home()
        self.db_path = self.root / "mmtrace.db"
        self.analyses_root = self.root / "analyses"
        self._reconcile_storage()

    def persist_analysis(self, snapshot: SnapshotInput) -> AnalysisDetail:
        _validate_analysis_id(snapshot.analysis_id)
        self.root.mkdir(parents=True, exist_ok=True)
        self.analyses_root.mkdir(parents=True, exist_ok=True)

        final_dir = self.analyses_root / snapshot.analysis_id
        if final_dir.exists():
            raise PersistenceError(f"analysis already exists: {snapshot.analysis_id}")

        temp_dir = Path(
            tempfile.mkdtemp(prefix=f".{snapshot.analysis_id}-", dir=self.root)
        )
        moved = False
        try:
            metadata = self._build_snapshot(snapshot, temp_dir)
            _validate_snapshot_files(temp_dir, metadata)

            with connect(self.db_path) as connection:
                connection.execute("BEGIN")
                self._insert_rows(connection, metadata)
                self._publish_snapshot(temp_dir, final_dir)
                moved = True
                self._commit(connection)

            return self.get_analysis(snapshot.analysis_id)
        except Exception:
            if moved:
                shutil.rmtree(final_dir, ignore_errors=True)
            else:
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def list_analyses(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        adapter: str | None = None,
        findings: str | None = None,
    ) -> list[AnalysisSummary]:
        clauses: list[str] = []
        params: list[object] = []

        if search:
            clauses.append(
                """
                (
                    lower(coalesce(trace_id, '')) LIKE ?
                    OR lower(coalesce(task, '')) LIKE ?
                    OR lower(coalesce(model, '')) LIKE ?
                    OR lower(source_filename) LIKE ?
                )
                """
            )
            needle = f"%{search.lower()}%"
            params.extend([needle, needle, needle, needle])
        if status:
            clauses.append("status = ?")
            params.append(status)
        if adapter:
            clauses.append("adapter = ?")
            params.append(adapter)
        if findings == "errors":
            clauses.append("error_count > 0")
        elif findings == "warnings":
            clauses.append("warning_count > 0")
        elif findings == "none":
            clauses.append("finding_count = 0")
        elif findings is not None:
            raise PersistenceError(f"unsupported findings filter: {findings}")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            f"SELECT * FROM analyses {where} "
            "ORDER BY analyzed_at DESC, analysis_id DESC"
        )

        with connect(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
            summaries = []
            for row in rows:
                summaries.append(
                    AnalysisSummary(
                        analysis_id=row["analysis_id"],
                        trace_id=row["trace_id"],
                        adapter=row["adapter"],
                        status=row["status"],
                        task=row["task"],
                        agent=row["agent"],
                        model=row["model"],
                        benchmark=row["benchmark"],
                        step_count=row["step_count"],
                        error_count=row["error_count"],
                        warning_count=row["warning_count"],
                        finding_count=row["finding_count"],
                        analyzed_at=row["analyzed_at"],
                        mmtrace_version=row["mmtrace_version"],
                        rule_hits=self._rule_hits(connection, row["analysis_id"]),
                    )
                )
            return summaries

    def get_analysis(self, analysis_id: str) -> AnalysisDetail:
        _validate_analysis_id(analysis_id)
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM analyses WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
            if row is None:
                raise KeyError(analysis_id)

            analysis_dir = self.analyses_root / analysis_id
            if not _is_valid_committed_snapshot_dir(analysis_dir, self.analyses_root):
                raise PersistenceError("persisted analysis snapshot is missing or corrupt")

            trace = _read_json(_resolve_stored_file(self.root, row["normalized_trace_relpath"]))
            report = _read_json(_resolve_stored_file(self.root, row["report_relpath"]))
            screenshots = self._screenshot_mapping(connection, analysis_id)

        return AnalysisDetail(
            analysis_id=analysis_id,
            trace=trace,
            report=report,
            artifacts={"screenshots": screenshots},
        )

    def artifact_path(self, analysis_id: str, stored_relpath: str) -> Path:
        _validate_analysis_id(analysis_id)
        normalized = _normalize_relpath(stored_relpath)
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT stored_relpath
                FROM artifacts
                WHERE analysis_id = ? AND stored_relpath = ?
                """,
                (analysis_id, normalized),
            ).fetchone()
            if row is None:
                raise KeyError(stored_relpath)

        root = self.analyses_root / analysis_id
        target = (self.root / row["stored_relpath"]).resolve()
        if not _is_relative_to(target, root.resolve()) or not target.is_file():
            raise KeyError(stored_relpath)
        return target

    def _build_snapshot(self, snapshot: SnapshotInput, temp_dir: Path) -> dict[str, object]:
        source_dir = temp_dir / "source"
        normalized_dir = temp_dir / "normalized"
        report_dir = temp_dir / "report"
        artifact_dir = temp_dir / "artifacts"
        source_dir.mkdir()
        normalized_dir.mkdir()
        report_dir.mkdir()
        artifact_dir.mkdir()

        source_filename = _safe_filename(snapshot.source_filename)
        source_target = source_dir / source_filename
        shutil.copyfile(snapshot.source_path, source_target)

        normalized_path = normalized_dir / "trace.json"
        normalized_path.write_text(
            snapshot.trace.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

        report_path = report_dir / "report.json"
        report_path.write_text(
            snapshot.report.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        _write_snapshot_manifest(temp_dir, snapshot.analysis_id)

        artifacts = []
        used_names: set[str] = set()
        for artifact in snapshot.artifacts:
            stored_name = _unique_safe_artifact_name(artifact.stored_name, used_names)
            stored_path = artifact_dir / stored_name
            shutil.copyfile(artifact.temp_path, stored_path)
            stat_result = stored_path.stat()
            artifacts.append(
                {
                    "artifact_id": str(uuid4()),
                    "analysis_id": snapshot.analysis_id,
                    "observation_id": artifact.observation_id,
                    "kind": artifact.kind,
                    "source_path": artifact.source_path,
                    "stored_relpath": _relpath(stored_path, temp_dir, snapshot.analysis_id),
                    "mime_type": artifact.mime_type
                    or mimetypes.guess_type(stored_name)[0],
                    "sha256": _sha256(stored_path),
                    "byte_size": stat_result.st_size,
                    "width": artifact.width,
                    "height": artifact.height,
                }
            )

        return {
            "analysis": {
                "analysis_id": snapshot.analysis_id,
                "trace_id": snapshot.trace.trace_id,
                "adapter": snapshot.adapter,
                "status": snapshot.report.status.value,
                "task": snapshot.trace.task,
                "agent": snapshot.trace.agent,
                "model": _metadata_text(snapshot.trace.metadata, "model"),
                "benchmark": _metadata_text(snapshot.trace.metadata, "benchmark"),
                "step_count": len(snapshot.trace.steps),
                "error_count": snapshot.report.error_count,
                "warning_count": snapshot.report.warning_count,
                "finding_count": len(snapshot.report.findings),
                "source_filename": source_filename,
                "source_sha256": _sha256(source_target),
                "analyzed_at": _utc_now_iso(),
                "mmtrace_version": _mmtrace_version(),
                "schema_version": SCHEMA_VERSION,
                "source_relpath": _relpath(source_target, temp_dir, snapshot.analysis_id),
                "normalized_trace_relpath": _relpath(
                    normalized_path,
                    temp_dir,
                    snapshot.analysis_id,
                ),
                "report_relpath": _relpath(report_path, temp_dir, snapshot.analysis_id),
            },
            "findings": [
                {
                    "analysis_id": snapshot.analysis_id,
                    "ordinal": ordinal,
                    "rule_id": finding.rule_id,
                    "severity": finding.severity.value,
                    "step_id": finding.step_id,
                    "title": finding.title,
                }
                for ordinal, finding in enumerate(snapshot.report.findings)
            ],
            "artifacts": artifacts,
        }

    def _insert_rows(self, connection, metadata: dict[str, object]) -> None:
        analysis = metadata["analysis"]
        connection.execute(
            """
            INSERT INTO analyses (
                analysis_id, trace_id, adapter, status, task, agent, model, benchmark,
                step_count, error_count, warning_count, finding_count,
                source_filename, source_sha256, analyzed_at, mmtrace_version,
                schema_version, source_relpath, normalized_trace_relpath, report_relpath
            )
            VALUES (
                :analysis_id, :trace_id, :adapter, :status, :task, :agent,
                :model, :benchmark, :step_count, :error_count, :warning_count,
                :finding_count, :source_filename, :source_sha256, :analyzed_at,
                :mmtrace_version, :schema_version, :source_relpath,
                :normalized_trace_relpath, :report_relpath
            )
            """,
            analysis,
        )
        connection.executemany(
            """
            INSERT INTO findings (
                analysis_id, ordinal, rule_id, severity, step_id, title
            )
            VALUES (
                :analysis_id, :ordinal, :rule_id, :severity, :step_id, :title
            )
            """,
            metadata["findings"],
        )
        connection.executemany(
            """
            INSERT INTO artifacts (
                artifact_id, analysis_id, observation_id, kind, source_path,
                stored_relpath, mime_type, sha256, byte_size, width, height
            )
            VALUES (
                :artifact_id, :analysis_id, :observation_id, :kind, :source_path,
                :stored_relpath, :mime_type, :sha256, :byte_size, :width, :height
            )
            """,
            metadata["artifacts"],
        )

    def _publish_snapshot(self, temp_dir: Path, final_dir: Path) -> None:
        os.replace(temp_dir, final_dir)

    def _commit(self, connection) -> None:
        connection.commit()

    def _reconcile_storage(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.analyses_root.mkdir(parents=True, exist_ok=True)

        with connect(self.db_path) as connection:
            committed_ids = {
                row["analysis_id"]
                for row in connection.execute("SELECT analysis_id FROM analyses").fetchall()
            }

        for candidate in self.analyses_root.iterdir():
            if not _is_reconcilable_orphan_candidate(candidate, self.analyses_root):
                continue
            if candidate.name in committed_ids:
                continue
            logger.warning("Removing orphaned MMTrace analysis snapshot %s", candidate.name)
            _safe_remove_analysis_dir(candidate, self.analyses_root)

    def _rule_hits(self, connection, analysis_id: str) -> list[RuleHit]:
        rows = connection.execute(
            """
            SELECT rule_id, severity, COUNT(*) AS count
            FROM findings
            WHERE analysis_id = ?
            GROUP BY rule_id, severity
            ORDER BY rule_id, severity
            """,
            (analysis_id,),
        ).fetchall()
        return [
            RuleHit(rule_id=row["rule_id"], severity=row["severity"], count=row["count"])
            for row in rows
        ]

    def _screenshot_mapping(self, connection, analysis_id: str) -> dict[str, str]:
        rows = connection.execute(
            """
            SELECT observation_id, stored_relpath
            FROM artifacts
            WHERE analysis_id = ? AND kind = 'screenshot' AND observation_id IS NOT NULL
            ORDER BY observation_id
            """,
            (analysis_id,),
        ).fetchall()
        return {
            row["observation_id"]: (
                f"/api/artifacts/{analysis_id}/{quote(row['stored_relpath'], safe='/')}"
            )
            for row in rows
        }


def mmtrace_home() -> Path:
    override = os.environ.get("MMTRACE_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".mmtrace"


def new_analysis_id() -> str:
    return str(uuid4())


def _validate_analysis_id(value: str) -> None:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise KeyError(value) from exc
    if str(parsed) != value:
        raise KeyError(value)


def _validate_snapshot_files(temp_dir: Path, metadata: dict[str, object]) -> None:
    analysis = metadata["analysis"]
    required = (
        analysis["source_relpath"],
        analysis["normalized_trace_relpath"],
        analysis["report_relpath"],
    )
    for relpath in required:
        path = temp_dir / Path(relpath).relative_to(f"analyses/{analysis['analysis_id']}")
        if not path.is_file():
            raise PersistenceError(f"required snapshot file missing: {relpath}")

    manifest = _read_snapshot_manifest(temp_dir / SNAPSHOT_MANIFEST)
    if manifest.get("analysis_id") != analysis["analysis_id"]:
        raise PersistenceError("snapshot manifest analysis_id mismatch")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise PersistenceError("snapshot manifest schema_version mismatch")


def _write_snapshot_manifest(snapshot_dir: Path, analysis_id: str) -> None:
    (snapshot_dir / SNAPSHOT_MANIFEST).write_text(
        json.dumps(
            {
                "format": SNAPSHOT_FORMAT,
                "analysis_id": analysis_id,
                "schema_version": SCHEMA_VERSION,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_snapshot_manifest(path: Path) -> dict[str, object]:
    try:
        with path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PersistenceError("invalid MMTrace snapshot manifest") from exc
    if not isinstance(manifest, dict):
        raise PersistenceError("invalid MMTrace snapshot manifest")
    if manifest.get("format") != SNAPSHOT_FORMAT:
        raise PersistenceError("invalid MMTrace snapshot format")
    return manifest


def _is_reconcilable_orphan_candidate(candidate: Path, analyses_root: Path) -> bool:
    if candidate.is_symlink() or not candidate.is_dir():
        return False
    if not _is_direct_child(candidate, analyses_root):
        return False
    try:
        _validate_analysis_id(candidate.name)
    except KeyError:
        return False

    manifest_path = candidate / SNAPSHOT_MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return False
    try:
        manifest = _read_snapshot_manifest(manifest_path)
    except PersistenceError:
        return False
    return (
        manifest.get("analysis_id") == candidate.name
        and manifest.get("schema_version") == SCHEMA_VERSION
    )


def _is_valid_committed_snapshot_dir(candidate: Path, analyses_root: Path) -> bool:
    return _is_reconcilable_orphan_candidate(candidate, analyses_root)


def _safe_remove_analysis_dir(candidate: Path, analyses_root: Path) -> None:
    if not _is_reconcilable_orphan_candidate(candidate, analyses_root):
        return
    if not _is_direct_child(candidate, analyses_root):
        return
    shutil.rmtree(candidate)


def _is_direct_child(candidate: Path, parent: Path) -> bool:
    try:
        return candidate.resolve().parent == parent.resolve()
    except OSError:
        return False


def _normalize_relpath(path: str) -> str:
    normalized = posixpath.normpath(path.replace("\\", "/"))
    if normalized in {"", "."} or normalized.startswith("../") or normalized == "..":
        raise KeyError(path)
    if normalized.startswith("/") or Path(normalized).is_absolute():
        raise KeyError(path)
    return normalized


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    return name or "trace.json"


def _unique_safe_artifact_name(filename: str, used_names: set[str]) -> str:
    base = _safe_filename(filename)
    stem = Path(base).stem or "artifact"
    suffix = Path(base).suffix
    candidate = base
    index = 1
    while candidate in used_names:
        candidate = f"{stem}-{index}{suffix}"
        index += 1
    used_names.add(candidate)
    return candidate


def _metadata_text(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return str(value) if value is not None else None


def _mmtrace_version() -> str:
    try:
        return version("mmtrace")
    except PackageNotFoundError as exc:
        raise PersistenceError("unable to resolve installed MMTrace package version") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_stored_file(root: Path, relpath: str) -> Path:
    normalized = _normalize_relpath(relpath)
    target = (root / normalized).resolve()
    if not _is_relative_to(target, root.resolve()) or not target.is_file():
        raise PersistenceError("persisted analysis snapshot file is missing or corrupt")
    return target


def _relpath(path: Path, snapshot_root: Path, analysis_id: str) -> str:
    return str(Path("analyses") / analysis_id / path.relative_to(snapshot_root))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def severity_rank(severity: str) -> int:
    order = {
        Severity.ERROR.value: 0,
        Severity.WARNING.value: 1,
        Severity.INFO.value: 2,
    }
    return order.get(severity, 3)

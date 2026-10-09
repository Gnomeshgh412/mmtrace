"""FastAPI backend for exposing MMTrace core checks over HTTP."""

from __future__ import annotations

import tempfile
import posixpath
import shutil
import stat
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from mmtrace.adapters.base import AdapterError, BaseAdapter
from mmtrace.adapters.browser_use import BrowserUseAdapter
from mmtrace.adapters.generic_json import GenericJSONAdapter
from mmtrace.adapters.holo4 import Holo4Adapter
from mmtrace.adapters.osworld import OSWorldAdapter
from mmtrace.engine import CheckEngine
from mmtrace.schema.trace import Observation, Trace
from web.backend.persistence import ArtifactInput, PersistenceError, PersistenceStore, SnapshotInput
from web.backend.persistence.models import AnalysisDetail, AnalysisSummary
from web.backend.persistence.store import new_analysis_id

app = FastAPI(title="MMTrace API")

ALLOWED_SCREENSHOT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_ARTIFACT_FILES = 500
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mmtrace"}


@app.post("/api/analyze")
async def analyze(
    adapter: str = Form(...),
    trace_file: UploadFile = File(...),
    artifacts: UploadFile | None = File(None),
) -> dict:
    selected_adapter = _adapter_for_name(adapter)
    temp_path = await _write_upload_to_temp_file(trace_file)
    artifact_zip_path = (
        await _write_upload_to_temp_file(artifacts, suffix=".zip")
        if artifacts is not None
        else None
    )
    analysis_id = new_analysis_id()
    artifact_root: Path | None = None
    extracted_artifacts: list[str] = []

    try:
        if artifact_zip_path is not None:
            artifact_root = Path(tempfile.mkdtemp(prefix=f"mmtrace-artifacts-{analysis_id}-"))
            extracted_artifacts = _extract_screenshot_zip(artifact_zip_path, artifact_root)

        load_path = temp_path
        if adapter == "osworld" and artifact_root is not None:
            load_path = artifact_root / _safe_uploaded_filename(trace_file.filename, "traj.jsonl")
            shutil.copyfile(temp_path, load_path)

        trace = selected_adapter.load(load_path)
        report = CheckEngine().run(trace)
        persisted = PersistenceStore().persist_analysis(
            SnapshotInput(
                analysis_id=analysis_id,
                adapter=adapter,
                source_path=temp_path,
                source_filename=_safe_uploaded_filename(trace_file.filename, "trace.json"),
                trace=trace,
                report=report,
                artifacts=(
                    _collect_screenshot_artifacts(trace, artifact_root, extracted_artifacts)
                    if artifact_root is not None
                    else []
                ),
            )
        )
        return persisted.model_dump(mode="json")
    except AdapterError as exc:
        raise _adapter_http_error(exc) from exc
    except zipfile.BadZipFile as exc:
        raise _error_response(
            status_code=400,
            code="INVALID_INPUT",
            message="Uploaded artifacts file is not a valid ZIP archive.",
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)
        if artifact_zip_path is not None:
            artifact_zip_path.unlink(missing_ok=True)
        if artifact_root is not None:
            shutil.rmtree(artifact_root, ignore_errors=True)


@app.get("/api/artifacts/{analysis_id}/{artifact_path:path}")
def get_artifact(analysis_id: str, artifact_path: str) -> FileResponse:
    try:
        target = PersistenceStore().artifact_path(analysis_id, artifact_path)
    except KeyError as exc:
        raise _error_response(
            status_code=404,
            code="INVALID_INPUT",
            message="Unknown analysis artifact.",
        ) from exc

    return FileResponse(target)


@app.get("/api/analyses", response_model=list[AnalysisSummary])
def list_analyses(
    search: str | None = None,
    status: str | None = None,
    adapter: str | None = None,
    findings: str | None = None,
) -> list[AnalysisSummary]:
    try:
        return PersistenceStore().list_analyses(
            search=search,
            status=status,
            adapter=adapter,
            findings=findings,
        )
    except (PersistenceError, ValueError) as exc:
        raise _error_response(
            status_code=400,
            code="INVALID_INPUT",
            message=str(exc),
        ) from exc


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisDetail)
def get_analysis(analysis_id: str) -> AnalysisDetail:
    try:
        return PersistenceStore().get_analysis(analysis_id)
    except KeyError as exc:
        raise _error_response(
            status_code=404,
            code="INVALID_INPUT",
            message="Unknown analysis.",
        ) from exc


def _adapter_for_name(name: str) -> BaseAdapter:
    if name == "generic":
        return GenericJSONAdapter()
    if name == "browser-use":
        return BrowserUseAdapter()
    if name == "osworld":
        return OSWorldAdapter()
    if name == "holo4":
        return Holo4Adapter()
    raise _error_response(
        status_code=400,
        code="UNKNOWN_ADAPTER",
        message=f"Unknown adapter: {name}",
    )


async def _write_upload_to_temp_file(upload: UploadFile, suffix: str = ".json") -> Path:
    try:
        content = await upload.read()
    except OSError as exc:
        raise _error_response(
            status_code=400,
            code="INVALID_INPUT",
            message=f"Failed to read uploaded file: {exc}",
        ) from exc

    if not content:
        raise _error_response(
            status_code=400,
            code="INVALID_INPUT",
            message="Uploaded trace_file is empty.",
        )

    temp = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=suffix,
        prefix="mmtrace-upload-",
        delete=False,
    )
    temp_path = Path(temp.name)
    try:
        with temp:
            temp.write(content)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise _error_response(
            status_code=400,
            code="INVALID_INPUT",
            message=f"Failed to stage uploaded file: {exc}",
        ) from exc

    return temp_path


def _prepare_screenshot_artifacts(
    analysis_id: str,
    trace: Trace,
    archive_path: Path,
) -> dict[str, str]:
    artifact_root = Path(tempfile.mkdtemp(prefix=f"mmtrace-artifacts-{analysis_id}-"))
    try:
        extracted = _extract_screenshot_zip(archive_path, artifact_root)
    except Exception:
        shutil.rmtree(artifact_root, ignore_errors=True)
        raise
    inputs = _collect_screenshot_artifacts(trace, artifact_root, extracted)
    return {
        artifact.observation_id or "": f"/api/artifacts/{analysis_id}/artifacts/{quote(artifact.stored_name, safe='')}"
        for artifact in inputs
        if artifact.observation_id
    }


def _collect_screenshot_artifacts(
    trace: Trace,
    artifact_root: Path,
    extracted: list[str],
) -> list[ArtifactInput]:
    if not extracted:
        return []

    by_path = {path: path for path in extracted}
    by_basename: dict[str, list[str]] = {}
    for path in extracted:
        by_basename.setdefault(posixpath.basename(path), []).append(path)

    artifacts: list[ArtifactInput] = []
    for observation in _iter_observations(trace):
        if not observation.observation_id or not observation.image_path:
            continue

        matched = _match_observation_screenshot(
            observation.image_path,
            by_path,
            by_basename,
        )
        if matched is None:
            continue

        extension = Path(matched).suffix.lower()
        stored_name = f"{_safe_artifact_stem(observation.observation_id)}{extension}"
        artifacts.append(
            ArtifactInput(
                observation_id=observation.observation_id,
                kind="screenshot",
                source_path=matched,
                temp_path=artifact_root / matched,
                stored_name=stored_name,
                width=observation.width,
                height=observation.height,
            )
        )

    return artifacts


def _safe_uploaded_filename(filename: str | None, fallback: str) -> str:
    if not filename:
        return fallback
    try:
        normalized = _normalize_artifact_path(Path(filename).name)
    except HTTPException:
        return fallback
    return normalized or fallback


def _safe_artifact_stem(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in value
    ).strip("-_")
    return safe or "artifact"


def _extract_screenshot_zip(archive_path: Path, destination: Path) -> list[str]:
    extracted: list[str] = []
    total_size = 0

    with zipfile.ZipFile(archive_path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_ARTIFACT_FILES:
            raise _error_response(
                status_code=400,
                code="INVALID_INPUT",
                message="Artifact ZIP contains too many files.",
            )

        for info in infos:
            if _is_zip_symlink(info):
                raise _error_response(
                    status_code=400,
                    code="INVALID_INPUT",
                    message="Artifact ZIP contains unsupported file entries.",
                )

            safe_name = _normalize_artifact_path(info.filename)
            if Path(safe_name).suffix.lower() not in ALLOWED_SCREENSHOT_EXTENSIONS:
                continue

            total_size += info.file_size
            if total_size > MAX_ARTIFACT_BYTES:
                raise _error_response(
                    status_code=400,
                    code="INVALID_INPUT",
                    message="Artifact ZIP exceeds the maximum extracted size.",
                )

            target = (destination / safe_name).resolve()
            if not _is_relative_to(target, destination.resolve()):
                raise _error_response(
                    status_code=400,
                    code="INVALID_INPUT",
                    message="Artifact ZIP contains an unsafe path.",
                )

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(safe_name)

    return extracted


def _normalize_artifact_path(path: str) -> str:
    normalized = posixpath.normpath(path.replace("\\", "/"))
    if normalized in {"", "."} or normalized.startswith("../") or normalized == "..":
        raise _error_response(
            status_code=400,
            code="INVALID_INPUT",
            message="Artifact path is unsafe.",
        )
    if normalized.startswith("/") or Path(normalized).is_absolute():
        raise _error_response(
            status_code=400,
            code="INVALID_INPUT",
            message="Artifact path is unsafe.",
        )
    return normalized


def _match_observation_screenshot(
    image_path: str,
    by_path: dict[str, str],
    by_basename: dict[str, list[str]],
) -> str | None:
    normalized = _normalize_trace_image_path(image_path)
    if normalized in by_path:
        return by_path[normalized]

    basename = posixpath.basename(image_path.replace("\\", "/"))
    candidates = by_basename.get(basename, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def _normalize_trace_image_path(path: str) -> str:
    normalized = posixpath.normpath(path.replace("\\", "/"))
    if normalized.startswith("/") or normalized.startswith("../") or normalized == "..":
        return posixpath.basename(normalized)
    return normalized


def _iter_observations(trace: Trace) -> list[Observation]:
    observations: list[Observation] = []
    seen: set[str] = set()
    for step in trace.steps:
        for observation in (
            step.observation,
            step.post_state.observation if step.post_state else None,
        ):
            if observation is None:
                continue
            key = observation.observation_id or id(observation)
            if str(key) in seen:
                continue
            seen.add(str(key))
            observations.append(observation)
    return observations


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _adapter_http_error(exc: AdapterError) -> HTTPException:
    message = str(exc)
    code = "INVALID_TRACE"
    status_code = 422

    if "invalid JSON" in message or "failed to parse" in message:
        code = "INVALID_INPUT"
        status_code = 400

    return _error_response(status_code=status_code, code=code, message=message)


def _error_response(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "INVALID_INPUT",
                "message": str(exc.detail),
            }
        },
    )


@app.exception_handler(Exception)
async def internal_exception_handler(_, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error.",
            }
        },
    )

"""FastAPI backend for exposing MMTrace core checks over HTTP."""

from __future__ import annotations

import tempfile
import posixpath
import shutil
import stat
import zipfile
from atexit import register as register_atexit
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from mmtrace.adapters.base import AdapterError, BaseAdapter
from mmtrace.adapters.browser_use import BrowserUseAdapter
from mmtrace.adapters.generic_json import GenericJSONAdapter
from mmtrace.engine import CheckEngine
from mmtrace.schema.trace import Observation, Trace

app = FastAPI(title="MMTrace API")

ALLOWED_SCREENSHOT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_ARTIFACT_FILES = 500
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
_ARTIFACT_REGISTRY: dict[str, Path] = {}


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
    analysis_id = str(uuid4())

    try:
        trace = selected_adapter.load(temp_path)
        report = CheckEngine().run(trace)
        screenshot_mapping = (
            _prepare_screenshot_artifacts(analysis_id, trace, artifact_zip_path)
            if artifact_zip_path is not None
            else {}
        )
        return {
            "analysis_id": analysis_id,
            "trace": trace.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
            "artifacts": {"screenshots": screenshot_mapping},
        }
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


@app.get("/api/artifacts/{analysis_id}/{artifact_path:path}")
def get_artifact(analysis_id: str, artifact_path: str) -> FileResponse:
    root = _ARTIFACT_REGISTRY.get(analysis_id)
    if root is None:
        raise _error_response(
            status_code=404,
            code="INVALID_INPUT",
            message="Unknown analysis artifact.",
        )

    safe_path = _normalize_artifact_path(artifact_path)
    target = (root / safe_path).resolve()
    if not _is_relative_to(target, root.resolve()) or not target.is_file():
        raise _error_response(
            status_code=404,
            code="INVALID_INPUT",
            message="Unknown analysis artifact.",
        )

    return FileResponse(target)


def _adapter_for_name(name: str) -> BaseAdapter:
    if name == "generic":
        return GenericJSONAdapter()
    if name == "browser-use":
        return BrowserUseAdapter()
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
    if not extracted:
        _ARTIFACT_REGISTRY[analysis_id] = artifact_root
        return {}

    _ARTIFACT_REGISTRY[analysis_id] = artifact_root
    by_path = {path: path for path in extracted}
    by_basename: dict[str, list[str]] = {}
    for path in extracted:
        by_basename.setdefault(posixpath.basename(path), []).append(path)

    mapping: dict[str, str] = {}
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

        mapping[observation.observation_id] = (
            f"/api/artifacts/{analysis_id}/{quote(matched, safe='/')}"
        )

    return mapping


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


def _cleanup_artifacts() -> None:
    for path in _ARTIFACT_REGISTRY.values():
        shutil.rmtree(path, ignore_errors=True)


register_atexit(_cleanup_artifacts)

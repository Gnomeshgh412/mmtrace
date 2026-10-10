"""Source-checkout web server entrypoint for MMTrace."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class ServeError(Exception):
    """User-facing serve startup error."""


def serve(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    root: Path | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    app_factory: Callable[[Path], Any] | None = None,
    run_server: Callable[..., Any] | None = None,
) -> int:
    """Run the source-checkout web UI with one uvicorn process."""
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    try:
        checkout_root = _source_checkout_root(root)
        frontend_dist = _frontend_dist(checkout_root)
        _validate_frontend_dist(frontend_dist)
        _ensure_source_checkout_on_path(checkout_root)
        app = (app_factory or create_serving_app)(frontend_dist)
    except ServeError as exc:
        print(f"MMTrace error: {exc}", file=stderr)
        return 2

    if host == "0.0.0.0":
        print(
            "Warning: binding to 0.0.0.0 may expose local traces and screenshots "
            "to other machines on the network.",
            file=stderr,
        )

    print(f"MMTrace running at http://{host}:{port}", file=stdout)

    if run_server is None:
        import uvicorn

        run_server = uvicorn.run
    run_server(app, host=host, port=port)
    return 0


def create_serving_app(frontend_dist: Path) -> Any:
    try:
        from web.backend.app import app, configure_frontend
    except ModuleNotFoundError as exc:
        if exc.name == "web" or exc.name.startswith("web."):
            raise ServeError(_not_source_checkout_message()) from exc
        raise

    return configure_frontend(app, frontend_dist)


def _source_checkout_root(root: Path | None = None) -> Path:
    checkout_root = (root or Path(__file__).resolve().parents[2]).resolve()
    if not (checkout_root / "web" / "backend").is_dir() or not (
        checkout_root / "web" / "frontend"
    ).is_dir():
        raise ServeError(_not_source_checkout_message())
    return checkout_root


def _frontend_dist(root: Path) -> Path:
    return root / "web" / "frontend" / "dist"


def _ensure_source_checkout_on_path(root: Path) -> None:
    root_string = str(root)
    if root_string not in sys.path:
        sys.path.insert(0, root_string)


def _validate_frontend_dist(frontend_dist: Path) -> None:
    if (frontend_dist / "index.html").is_file() and (frontend_dist / "assets").is_dir():
        return

    raise ServeError(
        "Frontend build not found.\n\n"
        "Build it first:\n\n"
        "  cd web/frontend\n"
        "  npm ci\n"
        "  npm run build\n\n"
        "Then run:\n\n"
        "  mmtrace serve"
    )


def _not_source_checkout_message() -> str:
    return (
        "MMTrace v0.2 web UI serving requires a source checkout. "
        "The installed package does not include frontend assets."
    )

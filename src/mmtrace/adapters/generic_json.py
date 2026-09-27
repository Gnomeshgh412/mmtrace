"""Generic JSON adapter for standard MMTrace JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mmtrace.adapters.base import AdapterError, BaseAdapter
from mmtrace.schema.trace import Trace


class GenericJSONAdapter(BaseAdapter):
    name = "generic_json"

    def can_load(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() == ".json"

    def load(self, path: str | Path) -> Trace:
        input_path = Path(path)

        try:
            raw_data = input_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise AdapterError(f"file not found: {input_path}") from exc
        except OSError as exc:
            raise AdapterError(f"failed to read {input_path}: {exc}") from exc

        try:
            data: Any = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"failed to parse {input_path}: invalid JSON at line {exc.lineno}, column {exc.colno}"
            ) from exc

        try:
            return Trace.model_validate(data)
        except ValidationError as exc:
            raise AdapterError(f"failed to validate {input_path}: {exc}") from exc


__all__ = ["GenericJSONAdapter"]


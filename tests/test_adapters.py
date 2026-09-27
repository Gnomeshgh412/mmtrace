from pathlib import Path

import pytest

from mmtrace.adapters.base import AdapterError
from mmtrace.adapters.generic_json import GenericJSONAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def test_generic_json_adapter_loads_valid_trace() -> None:
    trace = GenericJSONAdapter().load(FIXTURES / "valid_trace.json")

    assert trace.trace_id == "valid-trace"
    assert len(trace.steps) == 1
    assert trace.steps[0].observation is not None
    assert trace.steps[0].observation.observation_id == "obs-001"


def test_generic_json_adapter_fails_on_json_syntax_error(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text('{"trace_id": "broken",', encoding="utf-8")

    with pytest.raises(AdapterError, match="invalid JSON"):
        GenericJSONAdapter().load(bad_json)


def test_generic_json_adapter_fails_on_schema_invalid(tmp_path: Path) -> None:
    invalid_schema = tmp_path / "invalid_schema.json"
    invalid_schema.write_text('{"trace_id": "broken", "steps": "invalid"}', encoding="utf-8")

    with pytest.raises(AdapterError, match="failed to validate"):
        GenericJSONAdapter().load(invalid_schema)


def test_generic_json_adapter_fails_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    with pytest.raises(AdapterError, match="file not found"):
        GenericJSONAdapter().load(missing)


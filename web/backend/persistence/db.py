"""SQLite schema management for local MMTrace persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1


class PersistenceError(RuntimeError):
    """Raised when the local persistence layer cannot complete an operation."""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_schema(connection)
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    current_version = connection.execute("PRAGMA user_version").fetchone()[0]
    if current_version > SCHEMA_VERSION:
        raise PersistenceError(
            f"unsupported MMTrace persistence schema version: {current_version}"
        )
    if current_version == SCHEMA_VERSION:
        return
    if current_version != 0:
        raise PersistenceError(
            f"cannot migrate MMTrace persistence schema version: {current_version}"
        )

    connection.executescript(
        """
        CREATE TABLE analyses (
            analysis_id TEXT PRIMARY KEY,
            trace_id TEXT,
            adapter TEXT NOT NULL,
            status TEXT NOT NULL,
            task TEXT,
            agent TEXT,
            model TEXT,
            benchmark TEXT,
            step_count INTEGER NOT NULL,
            error_count INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            finding_count INTEGER NOT NULL,
            source_filename TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            analyzed_at TEXT NOT NULL,
            mmtrace_version TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            source_relpath TEXT NOT NULL,
            normalized_trace_relpath TEXT NOT NULL,
            report_relpath TEXT NOT NULL
        );

        CREATE TABLE findings (
            analysis_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            rule_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            step_id TEXT,
            title TEXT NOT NULL,
            PRIMARY KEY (analysis_id, ordinal),
            FOREIGN KEY (analysis_id)
                REFERENCES analyses(analysis_id)
                ON DELETE CASCADE
        );

        CREATE TABLE artifacts (
            artifact_id TEXT PRIMARY KEY,
            analysis_id TEXT NOT NULL,
            observation_id TEXT,
            kind TEXT NOT NULL,
            source_path TEXT,
            stored_relpath TEXT NOT NULL,
            mime_type TEXT,
            sha256 TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            width INTEGER,
            height INTEGER,
            FOREIGN KEY (analysis_id)
                REFERENCES analyses(analysis_id)
                ON DELETE CASCADE
        );

        CREATE INDEX idx_analyses_analyzed_at ON analyses(analyzed_at);
        CREATE INDEX idx_analyses_status ON analyses(status);
        CREATE INDEX idx_analyses_adapter ON analyses(adapter);
        CREATE INDEX idx_findings_analysis_id ON findings(analysis_id);
        CREATE INDEX idx_findings_rule_id ON findings(rule_id);
        CREATE INDEX idx_findings_severity ON findings(severity);
        CREATE INDEX idx_artifacts_analysis_id ON artifacts(analysis_id);
        CREATE INDEX idx_artifacts_analysis_observation
            ON artifacts(analysis_id, observation_id);

        PRAGMA user_version = 1;
        """
    )
    connection.commit()

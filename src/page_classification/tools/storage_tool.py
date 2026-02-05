"""Storage tool - persist validated classification results."""

import json
import os
from datetime import datetime
from pathlib import Path

from ..models.classification_result import StoredClassification


def init_storage(output_path: str, export_format: str = "jsonl") -> None:
    """
    Initialize storage - clear existing file to start fresh.
    For JSONL: delete file if exists, then create empty file.
    For SQLite: clear table or delete file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if output_path.endswith(".db"):
        # For SQLite, clear the table (or delete file to recreate)
        import sqlite3
        if path.exists():
            try:
                conn = sqlite3.connect(str(path))
                conn.execute("DELETE FROM classifications")
                conn.commit()
                conn.close()
            except sqlite3.OperationalError:
                # Table doesn't exist yet, delete file to recreate
                path.unlink()
    else:
        # For JSONL and other formats, delete file to start fresh, then create empty file
        if path.exists():
            path.unlink()
        # Create empty file immediately so it exists from the start
        path.touch()


def storage_tool(
    result: StoredClassification,
    output_path: str,
    export_format: str = "jsonl",
) -> None:
    """
    Persist validated classification result.
    Supports jsonl append mode.
    Writes and flushes immediately after each record.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = result.model_dump(mode="json")
    if isinstance(data.get("processed_at"), datetime):
        data["processed_at"] = data["processed_at"].isoformat()

    if export_format == "jsonl":
        # Use append mode and flush immediately
        with open(path, "a", encoding="utf-8", buffering=1) as f:  # Line buffering
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
            f.flush()  # Explicit flush to ensure data is written immediately
            try:
                os.fsync(f.fileno())  # Force write to disk
            except (OSError, AttributeError):
                # Some systems don't support fsync or file might not have fileno
                pass
    else:
        # Fallback: append to JSON array (simplified)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                arr = json.load(f)
        else:
            arr = []
        arr.append(data)
        with open(path, "w", encoding="utf-8", buffering=1) as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
            f.flush()  # Explicit flush
            try:
                os.fsync(f.fileno())  # Force write to disk
            except (OSError, AttributeError):
                # Some systems don't support fsync or file might not have fileno
                pass


def storage_tool_sqlite(
    result: StoredClassification,
    db_path: str,
) -> None:
    """Persist to SQLite for querying."""
    import sqlite3

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS classifications (
            url TEXT PRIMARY KEY,
            final_url TEXT,
            http_status INTEGER,
            labels TEXT,
            confidence REAL,
            matched_rules TEXT,
            rationale TEXT,
            evidence TEXT,
            needs_review INTEGER,
            ruleset_version TEXT,
            model_version TEXT,
            processed_at TEXT,
            fetch_mode TEXT,
            content_hash TEXT
        )
    """)
    data = result.model_dump(mode="json")
    processed_at = data.get("processed_at")
    if isinstance(processed_at, datetime):
        processed_at = processed_at.isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO classifications
        (url, final_url, http_status, labels, confidence, matched_rules, rationale,
         evidence, needs_review, ruleset_version, model_version, processed_at,
         fetch_mode, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["url"],
            data["final_url"],
            data.get("http_status"),
            json.dumps(data["labels"]),  # Store labels as JSON array
            data["confidence"],
            json.dumps(data["matched_rules"]),
            data["rationale"],
            json.dumps(data["evidence"]),
            1 if data["needs_review"] else 0,
            data["ruleset_version"],
            data["model_version"],
            processed_at,
            data["fetch_mode"],
            data.get("content_hash"),
        ),
    )
    conn.commit()
    conn.close()

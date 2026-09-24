"""Derived continuity store for Orchestrator phase 1.

The store is intentionally small and flat: it persists meaningful cycle
checkpoints as a local SQLite cache derived from the already-normalized cycle
metadata that the logging hooks produce.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

DEFAULT_CONTINUITY_DB_FILENAME = "project_memory.db"
CONTINUITY_TABLE_NAME = "continuity_checkpoints"
REQUEST_GROUP_PREFIX = "request_group:"
DERIVED_KEY_PREFIX = "derived:"
DEFAULT_SOURCE_KIND = "cycle_metadata"


def _find_repo_root(start: Optional[Path] = None) -> Path:
    current = Path(start or __file__).resolve()
    current = current if current.is_dir() else current.parent
    for _ in range(20):
        if (current / ".git").exists() or (current / "orchestrator.agent.md").exists() or (current / ".wiki" / "orchestrator").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path(__file__).resolve().parents[1]


def resolve_continuity_db_path(root: Optional[Path] = None, db_path: Optional[Path] = None) -> Path:
    if db_path:
        return Path(db_path)
    base_root = Path(root) if root else _find_repo_root(None)
    return base_root / ".wiki" / "orchestrator" / DEFAULT_CONTINUITY_DB_FILENAME


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = [str(value).strip()]
    return [_safe_text(item) for item in items if item]


def _merge_unique_text_lists(*sources: Any) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in _as_text_list(source):
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = value.strip() if isinstance(value, str) else str(value).strip()
        if text:
            return _safe_text(text)
    return _safe_text(default)


def _normalize_inline_text(value: Any) -> str:
    text = _first_text(value)
    if not text:
        return ""
    return " ".join(text.split())


def _collect_files_touched(metadata: Mapping[str, Any]) -> List[str]:
    return _merge_unique_text_lists(
        metadata.get("files_touched"),
        metadata.get("important_files"),
        metadata.get("intended_files"),
        metadata.get("target_files"),
        metadata.get("planned_files"),
        metadata.get("components_touched"),
        metadata.get("components_intended"),
        metadata.get("intended_components"),
    )


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_json_text(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return _safe_text(payload)


def _stable_sha1_hex(value: Any) -> str:
    payload = _stable_json_text(value).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _coerce_cycle_metadata(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = dict(metadata or {})
    request_title = _normalize_inline_text(_first_text(metadata.get("request_title"), metadata.get("title")))
    project_request = _normalize_inline_text(
        _first_text(
            metadata.get("project_request"),
            metadata.get("anchored_request"),
            metadata.get("request_anchor"),
            metadata.get("original_request"),
            metadata.get("root_request"),
            request_title,
            metadata.get("normalized_request"),
            metadata.get("summary"),
        )
    )
    normalized_request = _normalize_inline_text(
        _first_text(
            metadata.get("normalized_request"),
            metadata.get("request"),
            metadata.get("prompt"),
            metadata.get("user_request"),
            metadata.get("overview"),
            metadata.get("history"),
            project_request,
        )
    )
    session_id = _normalize_inline_text(_first_text(metadata.get("session_id"), metadata.get("health_session_id")))
    cycle_id = _normalize_inline_text(_first_text(metadata.get("cycle_id")))
    request_group_id = _normalize_inline_text(_first_text(metadata.get("request_group_id")))
    workspace_id = _normalize_inline_text(_first_text(metadata.get("workspace_id"), metadata.get("health_workspace_id")))
    summary = _normalize_inline_text(_first_text(metadata.get("summary"), metadata.get("overview"), metadata.get("history")))
    change_applied = _normalize_inline_text(_first_text(metadata.get("change_applied"), metadata.get("work_done"), metadata.get("overview")))
    observed_result = _normalize_inline_text(_first_text(metadata.get("observed_result"), metadata.get("technical_details")))
    decision = _normalize_inline_text(_first_text(metadata.get("decision")))
    next_action = _normalize_inline_text(_first_text(metadata.get("next_action"), metadata.get("next_steps")))
    files_touched = _collect_files_touched(metadata)
    source_kind = _normalize_inline_text(_first_text(metadata.get("source_kind"), default=DEFAULT_SOURCE_KIND))
    source_identifier = _normalize_inline_text(_first_text(metadata.get("source_identifier"), metadata.get("fingerprint"), metadata.get("cycle_id"), metadata.get("recorded_at_utc")))

    return {
        "request_group_id": request_group_id,
        "workspace_id": workspace_id,
        "session_id": session_id,
        "cycle_id": cycle_id,
        "project_request": project_request,
        "request_title": request_title,
        "normalized_request": normalized_request,
        "summary": summary,
        "files_touched": files_touched,
        "change_applied": change_applied,
        "observed_result": observed_result,
        "decision": decision,
        "next_action": next_action,
        "source_kind": source_kind,
        "source_identifier": source_identifier,
    }


def _has_meaningful_checkpoint(metadata: Mapping[str, Any]) -> bool:
    for key in (
        "request_group_id",
        "workspace_id",
        "session_id",
        "cycle_id",
        "project_request",
        "request_title",
        "normalized_request",
        "summary",
        "change_applied",
        "observed_result",
        "decision",
        "next_action",
    ):
        if _normalize_inline_text(metadata.get(key)):
            return True
    if _collect_files_touched(metadata):
        return True
    return False


def derive_continuity_key_source(metadata: Mapping[str, Any]) -> str:
    if _normalize_inline_text(metadata.get("request_group_id")):
        return "request_group_id"
    return "derived_hash"


def derive_continuity_key(metadata: Mapping[str, Any]) -> str:
    request_group_id = _normalize_inline_text(metadata.get("request_group_id"))
    if request_group_id:
        return f"{REQUEST_GROUP_PREFIX}{request_group_id}"

    canonical_payload = {
        "project_request": _normalize_inline_text(
            _first_text(
                metadata.get("project_request"),
                metadata.get("anchored_request"),
                metadata.get("request_anchor"),
                metadata.get("original_request"),
                metadata.get("root_request"),
                metadata.get("request_title"),
                metadata.get("title"),
                metadata.get("normalized_request"),
                metadata.get("summary"),
            )
        ),
        "request_title": _normalize_inline_text(_first_text(metadata.get("request_title"), metadata.get("title"))),
        "normalized_request": _normalize_inline_text(
            _first_text(
                metadata.get("normalized_request"),
                metadata.get("request"),
                metadata.get("prompt"),
                metadata.get("user_request"),
                metadata.get("summary"),
            )
        ),
        "workspace_id": _normalize_inline_text(_first_text(metadata.get("workspace_id"), metadata.get("health_workspace_id"))),
        "session_id": _normalize_inline_text(_first_text(metadata.get("session_id"), metadata.get("health_session_id"))),
        "cycle_id": _normalize_inline_text(_first_text(metadata.get("cycle_id"))),
    }
    digest = _stable_sha1_hex(canonical_payload)
    return f"{DERIVED_KEY_PREFIX}{digest}"


def _build_checkpoint_row(metadata: Mapping[str, Any], *, source_kind: Optional[str] = None, source_identifier: Optional[str] = None) -> Optional[Dict[str, Any]]:
    normalized = _coerce_cycle_metadata(metadata)
    if source_kind:
        normalized["source_kind"] = _normalize_inline_text(source_kind)
    if source_identifier:
        normalized["source_identifier"] = _normalize_inline_text(source_identifier)

    if not _has_meaningful_checkpoint(normalized):
        return None

    continuity_key_source = derive_continuity_key_source(normalized)
    continuity_key = derive_continuity_key(normalized)
    checkpoint_payload = {
        "continuity_key": continuity_key,
        "continuity_key_source": continuity_key_source,
        **{key: value for key, value in normalized.items() if key not in {"source_kind", "source_identifier"}},
    }
    checkpoint_hash = f"sha1:{_stable_sha1_hex(checkpoint_payload)}"
    checkpoint_json = _stable_json_text(checkpoint_payload)
    timestamp = _now_utc()

    return {
        "continuity_key": continuity_key,
        "continuity_key_source": continuity_key_source,
        "checkpoint_hash": checkpoint_hash,
        "request_group_id": normalized["request_group_id"],
        "workspace_id": normalized["workspace_id"],
        "session_id": normalized["session_id"],
        "cycle_id": normalized["cycle_id"],
        "project_request": normalized["project_request"],
        "request_title": normalized["request_title"],
        "normalized_request": normalized["normalized_request"],
        "summary": normalized["summary"],
        "change_applied": normalized["change_applied"],
        "observed_result": normalized["observed_result"],
        "decision": normalized["decision"],
        "next_action": normalized["next_action"],
        "source_kind": normalized["source_kind"],
        "source_identifier": normalized["source_identifier"],
        "checkpoint_json": checkpoint_json,
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
    }


def _parse_checkpoint_json(payload: Any) -> Dict[str, Any]:
    if not payload:
        return {}
    if isinstance(payload, dict):
        return dict(payload)
    if not isinstance(payload, str):
        return {"raw": payload}
    try:
        value = json.loads(payload)
    except Exception:
        return {"raw": payload}
    return value if isinstance(value, dict) else {"raw": value}


class ContinuityStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {CONTINUITY_TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    continuity_key TEXT NOT NULL,
                    continuity_key_source TEXT NOT NULL,
                    checkpoint_hash TEXT NOT NULL,
                    request_group_id TEXT NOT NULL DEFAULT '',
                    workspace_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    cycle_id TEXT NOT NULL DEFAULT '',
                    project_request TEXT NOT NULL DEFAULT '',
                    request_title TEXT NOT NULL DEFAULT '',
                    normalized_request TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    change_applied TEXT NOT NULL DEFAULT '',
                    observed_result TEXT NOT NULL DEFAULT '',
                    decision TEXT NOT NULL DEFAULT '',
                    next_action TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL DEFAULT '',
                    source_identifier TEXT NOT NULL DEFAULT '',
                    checkpoint_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{CONTINUITY_TABLE_NAME}_dedupe ON {CONTINUITY_TABLE_NAME}(continuity_key, checkpoint_hash)"
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{CONTINUITY_TABLE_NAME}_key ON {CONTINUITY_TABLE_NAME}(continuity_key, created_at_utc DESC)"
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{CONTINUITY_TABLE_NAME}_session ON {CONTINUITY_TABLE_NAME}(session_id, created_at_utc DESC)"
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{CONTINUITY_TABLE_NAME}_cycle ON {CONTINUITY_TABLE_NAME}(cycle_id, created_at_utc DESC)"
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{CONTINUITY_TABLE_NAME}_request_group ON {CONTINUITY_TABLE_NAME}(request_group_id, created_at_utc DESC)"
            )

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute(f"DELETE FROM {CONTINUITY_TABLE_NAME}")

    def persist_checkpoint_record(self, checkpoint: Mapping[str, Any]) -> Dict[str, Any]:
        row = dict(checkpoint)
        if not row:
            raise ValueError("checkpoint must not be empty")

        params = {
            "continuity_key": _safe_text(row.get("continuity_key")),
            "continuity_key_source": _safe_text(row.get("continuity_key_source")),
            "checkpoint_hash": _safe_text(row.get("checkpoint_hash")),
            "request_group_id": _safe_text(row.get("request_group_id")),
            "workspace_id": _safe_text(row.get("workspace_id")),
            "session_id": _safe_text(row.get("session_id")),
            "cycle_id": _safe_text(row.get("cycle_id")),
            "project_request": _safe_text(row.get("project_request")),
            "request_title": _safe_text(row.get("request_title")),
            "normalized_request": _safe_text(row.get("normalized_request")),
            "summary": _safe_text(row.get("summary")),
            "change_applied": _safe_text(row.get("change_applied")),
            "observed_result": _safe_text(row.get("observed_result")),
            "decision": _safe_text(row.get("decision")),
            "next_action": _safe_text(row.get("next_action")),
            "source_kind": _safe_text(row.get("source_kind")),
            "source_identifier": _safe_text(row.get("source_identifier")),
            "checkpoint_json": _safe_text(row.get("checkpoint_json")),
            "created_at_utc": _safe_text(row.get("created_at_utc") or _now_utc()),
            "updated_at_utc": _safe_text(row.get("updated_at_utc") or _now_utc()),
        }

        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT OR IGNORE INTO {CONTINUITY_TABLE_NAME} (
                    continuity_key,
                    continuity_key_source,
                    checkpoint_hash,
                    request_group_id,
                    workspace_id,
                    session_id,
                    cycle_id,
                    project_request,
                    request_title,
                    normalized_request,
                    summary,
                    change_applied,
                    observed_result,
                    decision,
                    next_action,
                    source_kind,
                    source_identifier,
                    checkpoint_json,
                    created_at_utc,
                    updated_at_utc
                ) VALUES (
                    :continuity_key,
                    :continuity_key_source,
                    :checkpoint_hash,
                    :request_group_id,
                    :workspace_id,
                    :session_id,
                    :cycle_id,
                    :project_request,
                    :request_title,
                    :normalized_request,
                    :summary,
                    :change_applied,
                    :observed_result,
                    :decision,
                    :next_action,
                    :source_kind,
                    :source_identifier,
                    :checkpoint_json,
                    :created_at_utc,
                    :updated_at_utc
                )
                """,
                params,
            )
            connection.commit()

        latest = self._lookup_latest(params["continuity_key"])
        return latest or self._row_to_checkpoint_view(params)

    def persist_normalized_metadata(
        self,
        metadata: Mapping[str, Any],
        *,
        source_kind: Optional[str] = None,
        source_identifier: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        row = _build_checkpoint_row(metadata, source_kind=source_kind, source_identifier=source_identifier)
        if row is None:
            return None
        return self.persist_checkpoint_record(row)

    def _lookup_by_key(self, continuity_key: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        continuity_key = _safe_text(continuity_key)
        if not continuity_key:
            return []

        query = f"SELECT * FROM {CONTINUITY_TABLE_NAME} WHERE continuity_key = ? ORDER BY created_at_utc DESC, id DESC"
        params: List[Any] = [continuity_key]
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_view(row) for row in rows]

    def _lookup_latest(self, continuity_key: str) -> Optional[Dict[str, Any]]:
        rows = self._lookup_by_key(continuity_key, limit=1)
        return rows[0] if rows else None

    def rebuild_from_records(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        replace: bool = False,
        source_kind: str = "rebuild",
        source_identifier: str = "",
    ) -> int:
        if replace:
            self.clear()

        count = 0
        for record in records:
            if not isinstance(record, Mapping):
                continue
            persisted = self.persist_normalized_metadata(
                record,
                source_kind=source_kind,
                source_identifier=source_identifier,
            )
            if persisted is not None:
                count += 1
        return count

    def _row_to_view(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        payload = _parse_checkpoint_json(row["checkpoint_json"])
        return {
            "id": int(row["id"]),
            "continuity_key": _safe_text(row["continuity_key"]),
            "continuity_key_source": _safe_text(row["continuity_key_source"]),
            "checkpoint_hash": _safe_text(row["checkpoint_hash"]),
            "request_group_id": _safe_text(row["request_group_id"]),
            "workspace_id": _safe_text(row["workspace_id"]),
            "session_id": _safe_text(row["session_id"]),
            "cycle_id": _safe_text(row["cycle_id"]),
            "project_request": _safe_text(row["project_request"]),
            "request_title": _safe_text(row["request_title"]),
            "normalized_request": _safe_text(row["normalized_request"]),
            "summary": _safe_text(row["summary"]),
            "change_applied": _safe_text(row["change_applied"]),
            "observed_result": _safe_text(row["observed_result"]),
            "decision": _safe_text(row["decision"]),
            "next_action": _safe_text(row["next_action"]),
            "source_kind": _safe_text(row["source_kind"]),
            "source_identifier": _safe_text(row["source_identifier"]),
            "checkpoint_json": _safe_text(row["checkpoint_json"]),
            "created_at_utc": _safe_text(row["created_at_utc"]),
            "updated_at_utc": _safe_text(row["updated_at_utc"]),
            "checkpoint": payload,
        }

    def _row_to_checkpoint_view(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        payload = _parse_checkpoint_json(row.get("checkpoint_json"))
        return {
            "id": 0,
            "continuity_key": _safe_text(row.get("continuity_key")),
            "continuity_key_source": _safe_text(row.get("continuity_key_source")),
            "checkpoint_hash": _safe_text(row.get("checkpoint_hash")),
            "request_group_id": _safe_text(row.get("request_group_id")),
            "workspace_id": _safe_text(row.get("workspace_id")),
            "session_id": _safe_text(row.get("session_id")),
            "cycle_id": _safe_text(row.get("cycle_id")),
            "project_request": _safe_text(row.get("project_request")),
            "request_title": _safe_text(row.get("request_title")),
            "normalized_request": _safe_text(row.get("normalized_request")),
            "summary": _safe_text(row.get("summary")),
            "change_applied": _safe_text(row.get("change_applied")),
            "observed_result": _safe_text(row.get("observed_result")),
            "decision": _safe_text(row.get("decision")),
            "next_action": _safe_text(row.get("next_action")),
            "source_kind": _safe_text(row.get("source_kind")),
            "source_identifier": _safe_text(row.get("source_identifier")),
            "checkpoint_json": _safe_text(row.get("checkpoint_json")),
            "created_at_utc": _safe_text(row.get("created_at_utc")),
            "updated_at_utc": _safe_text(row.get("updated_at_utc")),
            "checkpoint": payload,
        }


def persist_continuity_checkpoint_from_normalized_metadata(
    metadata: Mapping[str, Any],
    *,
    root: Optional[Path] = None,
    db_path: Optional[Path] = None,
    source_kind: Optional[str] = None,
    source_identifier: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    store = ContinuityStore(resolve_continuity_db_path(root=root, db_path=db_path))
    return store.persist_normalized_metadata(
        metadata,
        source_kind=source_kind,
        source_identifier=source_identifier,
    )


def rebuild_continuity_store_from_records(
    records: Iterable[Mapping[str, Any]],
    *,
    root: Optional[Path] = None,
    db_path: Optional[Path] = None,
    replace: bool = False,
    source_kind: str = "rebuild",
    source_identifier: str = "",
) -> int:
    store = ContinuityStore(resolve_continuity_db_path(root=root, db_path=db_path))
    return store.rebuild_from_records(
        records,
        replace=replace,
        source_kind=source_kind,
        source_identifier=source_identifier,
    )


def rebuild_continuity_store_from_telemetry(
    root: Optional[Path] = None,
    *,
    db_path: Optional[Path] = None,
    replace: bool = False,
) -> int:
    base_root = Path(root) if root else _find_repo_root(None)
    telemetry_path = base_root / ".wiki" / "orchestrator" / "telemetry" / "cycles.jsonl"
    store = ContinuityStore(resolve_continuity_db_path(root=root, db_path=db_path))
    if replace:
        store.clear()
    count = 0
    if not telemetry_path.exists():
        return count
    with telemetry_path.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except Exception:
                continue
            if not isinstance(record, Mapping):
                continue
            persisted = store.persist_normalized_metadata(
                record,
                source_kind="telemetry_cycle",
                source_identifier=_first_text(record.get("fingerprint"), record.get("recorded_at_utc"), record.get("cycle_id")),
            )
            if persisted is not None:
                count += 1
    return count


__all__ = [
    "ContinuityStore",
    "DEFAULT_CONTINUITY_DB_FILENAME",
    "DEFAULT_SOURCE_KIND",
    "DERIVED_KEY_PREFIX",
    "REQUEST_GROUP_PREFIX",
    "derive_continuity_key",
    "derive_continuity_key_source",
    "persist_continuity_checkpoint_from_normalized_metadata",
    "rebuild_continuity_store_from_records",
    "rebuild_continuity_store_from_telemetry",
    "resolve_continuity_db_path",
]

"""Gateway for the existing Test/Production PHP CRUD APIs.

This app never connects directly to SQL Server and never sends arbitrary SQL.
The API contract uses action/table/filters/data/where/columns/orderBy/fetchAll.
"""
from __future__ import annotations
import re
from typing import Any
import requests

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*(?:\.[A-Za-z_][A-Za-z0-9_ ]*)?$")

def quote_identifier(name: str) -> str:
    name = str(name or "").strip()
    if not IDENT_RE.fullmatch(name) or "]" in name or "[" in name:
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return ".".join("[" + part.strip() + "]" for part in name.split("."))

def _normalise_rows(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [dict(row) for row in body if isinstance(row, dict)]
    if not isinstance(body, dict):
        return []
    for key in ("data", "rows", "result", "recordset"):
        value = body.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            for inner_key in ("rows", "data", "recordset"):
                inner = value.get(inner_key)
                if isinstance(inner, list):
                    return [dict(row) for row in inner if isinstance(row, dict)]
    return []


def _canonical_field_name(value: Any) -> str:
    """Compare legacy compact keys with the exact SQL column labels."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


# The verified Test_OperationsDB schema uses compact column names. Callers may
# still pass legacy labels with spaces; map both spellings to the exact physical
# SQL Server identifiers returned by INFORMATION_SCHEMA.
_COMMENT_LOG_COLUMNS = {
    _canonical_field_name(name): name
    for name in (
        "RecordID", "CommentID", "FMSRefId", "TaskID", "StageName",
        "AppID", "AppName", "Text", "AttachmentURL", "Timestamp",
        "Sender", "Receiver", "AttachmentFilename", "Type", "AskID",
        "Status", "NotificationMessage", "OpenThread", "CompleteStatus",
        "UniqueID", "ThreadID", "ThreadColor", "Unique", "ExtractedText",
        "TimestampInText",
    )
}

_STAGE_MAP_COLUMNS = {
    _canonical_field_name(name): name
    for name in ("TableName", "FMSRefId", "AppID", "StageNo")
}


def _table_leaf(table: str) -> str:
    return str(table or "").strip().split(".")[-1].strip().casefold()


def _normalise_table_fields(
    table: str,
    fields: dict[str, Any] | None,
    *,
    drop_comment_context_only_fields: bool = False,
) -> dict[str, Any]:
    """Translate aliases to the verified compact SQL column names at the API boundary.

    FMS_Comment_Log does NOT contain TableName or Stage No; these belong to
    FMS_Comment_FMS_Stage_Map. Older UI/backend builds may still include them
    in the insert object, so omit them only for comment-log INSERT payloads.
    They are rejected in filters/updates to avoid accidentally broad queries. The physical comment-log columns are compact (for example CommentID and FMSRefId).
    """
    table_key = _table_leaf(table)
    if table_key == "fms_comment_log":
        aliases = _COMMENT_LOG_COLUMNS
        context_only = {"tablename", "stageno"}
    elif table_key == "fms_comment_fms_stage_map":
        aliases = _STAGE_MAP_COLUMNS
        context_only = set()
    else:
        return dict(fields or {})

    output: dict[str, Any] = {}
    for raw_name, value in (fields or {}).items():
        canonical = _canonical_field_name(raw_name)
        if canonical in context_only:
            if drop_comment_context_only_fields:
                continue
            raise ValueError(
                f"Column {raw_name!r} is not a column in {table_key}; "
                "TableName and Stage No belong to FMS_Comment_FMS_Stage_Map."
            )
        output[aliases.get(canonical, raw_name)] = value
    return output


class HttpSqlGateway:
    """Adapter for the existing PHP CRUD API (apiv2.php Test / apiv3.php Production).

    The current Portal API contract is CRUD JSON, not raw SQL: SELECT uses
    ``filters``/``columns``/``orderBy``/``fetchAll``; INSERT uses ``data``;
    UPDATE uses ``data`` and ``where``. Values are never interpolated into SQL
    by this Python application.
    """
    def __init__(self, base_url: str, token: str = "", timeout: float = 20,
                 production: bool = False, allow_production_writes: bool = False):
        self.base_url = base_url.strip()
        self.token = token.strip()
        self.timeout = timeout
        self.production = production
        self.allow_production_writes = allow_production_writes
        self.session = requests.Session()

    def _request(self, payload: dict[str, Any], write: bool = False) -> Any:
        if not self.base_url:
            raise RuntimeError(
                "The selected SQL API URL is not configured. Set TEST_SQL_API_URL "
                "or PRODUCTION_SQL_API_URL in .env; use SQL_API_MODE=mock for safe local testing."
            )
        if write:
            self._write_guard()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.session.post(self.base_url, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("SQL API returned non-JSON content") from exc
        if isinstance(body, dict) and body.get("success") is False:
            raise RuntimeError(str(body.get("error") or body.get("message") or "SQL API request failed"))
        if isinstance(body, dict) and str(body.get("status", "")).lower() == "error":
            raise RuntimeError(str(body.get("error") or body.get("message") or "SQL API request failed"))
        return body

    @staticmethod
    def _validate_table(table: str) -> str:
        # The existing PHP CRUD API sanitizes table identifiers and strips the
        # schema separator. Sending "dbo.FMS_Comment_Log" therefore reaches SQL
        # Server as the invalid object "dboFMS_Comment_Log". Validate first,
        # then send the unqualified table name; SQL Server resolves it in the
        # API connection's default schema (normally dbo).
        cleaned = str(table or "").strip()
        quote_identifier(cleaned)
        parts = [part.strip() for part in cleaned.split(".")]
        if len(parts) == 2:
            schema, table_name = parts
            if schema.casefold() != "dbo":
                raise ValueError(
                    "The configured SQL CRUD API does not safely preserve schema-qualified table names. "
                    "Use the unqualified table name in SQL_*_TABLE settings."
                )
            return table_name
        return cleaned

    @staticmethod
    def _validate_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in (filters or {}).items():
            quote_identifier(key)
            result[key] = list(value) if isinstance(value, (set, tuple)) else value
        return result

    @staticmethod
    def _normalise_order_by(order_by: str) -> str:
        if not order_by:
            return ""
        parts: list[str] = []
        for item in order_by.split(","):
            tokens = item.strip().split()
            if not tokens:
                continue
            quote_identifier(tokens[0])
            direction = tokens[1].upper() if len(tokens) > 1 else "ASC"
            if direction not in {"ASC", "DESC"} or len(tokens) > 2:
                raise ValueError("Invalid ORDER BY expression")
            # Bracketing helps with the requested fields that contain spaces.
            parts.append(f"[{tokens[0]}] {direction}")
        return ", ".join(parts)

    def select(self, table: str, where: dict[str, Any] | None = None, order_by: str = "") -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "action": "select",
            "table": self._validate_table(table),
            "filters": self._validate_filters(_normalise_table_fields(table, where)),
            "fetchAll": True,
        }
        if order_by:
            payload["orderBy"] = self._normalise_order_by(order_by)
        body = self._request(payload, write=False)
        return _normalise_rows(body)

    def insert(self, table: str, values: dict[str, Any]) -> Any:
        if not values:
            raise ValueError("Cannot insert an empty record")
        self._write_guard()
        safe_values = _normalise_table_fields(
            table, values, drop_comment_context_only_fields=True
        )
        for column in safe_values:
            quote_identifier(column)
        return self._request({
            "action": "insert",
            "table": self._validate_table(table),
            "data": safe_values,
        }, write=True)

    def update(self, table: str, values: dict[str, Any], where: dict[str, Any]) -> Any:
        if not values:
            raise ValueError("Cannot update without values")
        if not where:
            raise ValueError("Refusing to update without a WHERE filter")
        self._write_guard()
        safe_values = _normalise_table_fields(table, values)
        safe_where = _normalise_table_fields(table, where)
        for column in safe_values:
            quote_identifier(column)
        return self._request({
            "action": "update",
            "table": self._validate_table(table),
            "data": safe_values,
            "where": self._validate_filters(safe_where),
        }, write=True)

    def _write_guard(self) -> None:
        if self.production and not self.allow_production_writes:
            raise PermissionError(
                "Production writes are blocked. Set ALLOW_PRODUCTION_WRITES=true explicitly to enable them."
            )

class MemorySqlGateway:
    """Small in-memory adapter used only by local previews and tests; it is not a data store for deployment."""
    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None):
        self.tables = {name: [dict(row) for row in rows] for name, rows in (tables or {}).items()}
        self._next_record_id = 1
        for rows in self.tables.values():
            for row in rows:
                if isinstance(row.get("RecordID"), int):
                    self._next_record_id = max(self._next_record_id, row["RecordID"] + 1)

    @staticmethod
    def _equal(actual: Any, expected: Any) -> bool:
        if isinstance(expected, (list, tuple, set)):
            return any(MemorySqlGateway._equal(actual, item) for item in expected)
        if actual is None or expected is None:
            return actual is expected
        return str(actual).strip().casefold() == str(expected).strip().casefold()

    def select(self, table: str, where: dict[str, Any] | None = None, order_by: str = "") -> list[dict[str, Any]]:
        rows = self.tables.setdefault(table, [])
        found = [dict(row) for row in rows if not where or all(self._equal(row.get(key), val) for key, val in where.items())]
        if order_by:
            item = order_by.split(",")[0].strip().split()
            col = item[0]
            reverse = len(item) > 1 and item[1].upper() == "DESC"
            found.sort(key=lambda r: str(r.get(col) or ""), reverse=reverse)
        return found

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        row = dict(values)
        if "RecordID" not in row:
            row["RecordID"] = self._next_record_id
            self._next_record_id += 1
        self.tables.setdefault(table, []).append(row)
        return {"success": True, "rowsAffected": 1, "data": row}

    def update(self, table: str, values: dict[str, Any], where: dict[str, Any]) -> dict[str, Any]:
        if not where:
            raise ValueError("Refusing to update without a WHERE filter")
        changed = 0
        for row in self.tables.setdefault(table, []):
            if all(self._equal(row.get(key), val) for key, val in where.items()):
                row.update(values)
                changed += 1
        return {"success": True, "rowsAffected": changed}

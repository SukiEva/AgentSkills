from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
import re
from typing import Any, Generator, Optional

from dws_mcp_server.config import DwsMcpSettings

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - 依赖未安装时用于更友好的报错
    psycopg2 = None
    RealDictCursor = None


MUTATING_PREFIXES = {
    "alter",
    "call",
    "cluster",
    "comment",
    "copy",
    "create",
    "delete",
    "drop",
    "grant",
    "insert",
    "merge",
    "refresh",
    "reindex",
    "revoke",
    "truncate",
    "update",
    "vacuum",
}

READ_ONLY_PREFIXES = {
    "describe",
    "desc",
    "explain",
    "select",
    "show",
    "values",
}


def _strip_leading_comments(sql_text: str) -> str:
    cleaned = sql_text.strip()
    cleaned = re.sub(r"^/\*.*?\*/\s*", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"^(?:--[^\n]*\n\s*)+", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def _ensure_single_statement(sql_text: str) -> None:
    statement_count = len([part for part in sql_text.split(";") if part.strip()])
    if statement_count > 1:
        raise ValueError("当前服务仅允许一次执行一条 SQL 语句。")


def classify_sql(sql_text: str) -> dict[str, Any]:
    normalized = _strip_leading_comments(sql_text).lower()
    if not normalized:
        raise ValueError("SQL 不能为空。")

    _ensure_single_statement(normalized)

    first_token = normalized.split(None, 1)[0]
    is_mutating = first_token in MUTATING_PREFIXES
    is_read_only = first_token in READ_ONLY_PREFIXES

    if first_token == "with":
        if re.search(r"\b(insert|update|delete|merge|create|alter|drop|truncate)\b", normalized):
            is_mutating = True
            is_read_only = False
        else:
            is_read_only = True

    return {
        "statement_type": first_token,
        "is_mutating": is_mutating,
        "is_read_only": is_read_only,
    }


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


class DwsDatabase:
    def __init__(self, settings: DwsMcpSettings) -> None:
        self.settings = settings

    def _ensure_driver(self) -> None:
        if psycopg2 is None or RealDictCursor is None:
            raise RuntimeError(
                "未安装 psycopg2-binary。请先在 mcp/dws-mcp-server 目录执行 `uv sync`。"
            )

    @contextmanager
    def connect(self) -> Generator[Any, None, None]:
        self._ensure_driver()

        connection = psycopg2.connect(
            host=self.settings.host,
            port=self.settings.port,
            dbname=self.settings.database,
            user=self.settings.user,
            password=self.settings.password,
            sslmode=self.settings.sslmode,
            connect_timeout=self.settings.connect_timeout,
            application_name=self.settings.app_name,
        )
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET statement_timeout = %s;",
                    (self.settings.statement_timeout_ms,),
                )
            yield connection
        finally:
            connection.close()

    def fetch_all(
        self,
        sql_text: str,
        params: Optional[tuple[Any, ...]] = None,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql_text, params or ())
            rows = cursor.fetchall()
        return _to_jsonable(rows)

    def fetch_one(
        self,
        sql_text: str,
        params: Optional[tuple[Any, ...]] = None,
    ) -> Optional[dict[str, Any]]:
        with self.connect() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql_text, params or ())
            row = cursor.fetchone()
        if row is None:
            return None
        return _to_jsonable(row)

    def execute_sql(
        self,
        sql_text: str,
        row_limit: Optional[int] = None,
        allow_mutation: bool = False,
    ) -> dict[str, Any]:
        classification = classify_sql(sql_text)
        effective_limit = self.settings.clamp_row_limit(row_limit)

        if classification["is_mutating"] and not (self.settings.allow_mutation and allow_mutation):
            raise ValueError(
                "当前服务默认禁止执行写入/DDL 语句。若确需执行，请同时设置 "
                "`DWS_ALLOW_MUTATION=true` 并在工具入参中传入 `allow_mutation=true`。"
            )

        with self.connect() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql_text)

            if cursor.description:
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchmany(effective_limit + 1)
                truncated = len(rows) > effective_limit
                if truncated:
                    rows = rows[:effective_limit]
                return {
                    "statement_type": classification["statement_type"],
                    "row_limit": effective_limit,
                    "truncated": truncated,
                    "row_count": len(rows),
                    "columns": columns,
                    "rows": _to_jsonable(rows),
                    "status": cursor.statusmessage,
                }

            return {
                "statement_type": classification["statement_type"],
                "row_limit": effective_limit,
                "truncated": False,
                "row_count": cursor.rowcount,
                "columns": [],
                "rows": [],
                "status": cursor.statusmessage,
            }

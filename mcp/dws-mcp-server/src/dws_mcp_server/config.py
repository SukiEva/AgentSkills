from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _read_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


@dataclass(frozen=True)
class DwsMcpSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str
    connect_timeout: int
    statement_timeout_ms: int
    default_row_limit: int
    max_row_limit: int
    allow_mutation: bool
    app_name: str

    @classmethod
    def from_env(cls) -> "DwsMcpSettings":
        settings = cls(
            host=os.getenv("DWS_HOST", "").strip(),
            port=_read_int("DWS_PORT", 8000),
            database=os.getenv("DWS_DATABASE", "").strip(),
            user=os.getenv("DWS_USER", "").strip(),
            password=os.getenv("DWS_PASSWORD", "").strip(),
            sslmode=os.getenv("DWS_SSLMODE", "prefer").strip() or "prefer",
            connect_timeout=_read_int("DWS_CONNECT_TIMEOUT", 10),
            statement_timeout_ms=_read_int("DWS_STATEMENT_TIMEOUT_MS", 120000),
            default_row_limit=_read_int("DWS_DEFAULT_ROW_LIMIT", 200),
            max_row_limit=_read_int("DWS_MAX_ROW_LIMIT", 2000),
            allow_mutation=_read_bool("DWS_ALLOW_MUTATION", False),
            app_name=os.getenv("DWS_APP_NAME", "dws-mcp-server").strip() or "dws-mcp-server",
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        missing = []
        if not self.host:
            missing.append("DWS_HOST")
        if not self.database:
            missing.append("DWS_DATABASE")
        if not self.user:
            missing.append("DWS_USER")
        if not self.password:
            missing.append("DWS_PASSWORD")
        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(f"缺少必填环境变量：{missing_text}")

        if self.default_row_limit <= 0:
            raise ValueError("DWS_DEFAULT_ROW_LIMIT 必须大于 0")
        if self.max_row_limit < self.default_row_limit:
            raise ValueError("DWS_MAX_ROW_LIMIT 不能小于 DWS_DEFAULT_ROW_LIMIT")

    def clamp_row_limit(self, row_limit: Optional[int]) -> int:
        if row_limit is None:
            return self.default_row_limit
        return max(1, min(row_limit, self.max_row_limit))

    def safe_summary(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout,
            "statement_timeout_ms": self.statement_timeout_ms,
            "default_row_limit": self.default_row_limit,
            "max_row_limit": self.max_row_limit,
            "allow_mutation": self.allow_mutation,
            "app_name": self.app_name,
        }

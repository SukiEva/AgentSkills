from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from .config import DwsMcpSettings
from .database import DwsDatabase
from .service import DwsMcpService

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - 未安装依赖时给出明确提示
    raise RuntimeError(
        "未安装 fastmcp。请先在 mcp/dws-mcp-server 目录执行 `uv sync`。"
    ) from exc


mcp = FastMCP("dws-mcp-server")


@lru_cache(maxsize=1)
def get_service() -> DwsMcpService:
    settings = DwsMcpSettings.from_env()
    database = DwsDatabase(settings)
    return DwsMcpService(database)


@mcp.tool
def ping() -> dict[str, Any]:
    """检查 DWS 连接、当前库信息和基础配置。"""
    return get_service().ping()


@mcp.tool
def list_schemas() -> dict[str, Any]:
    """列出当前 DWS 集群中可见的业务 Schema。"""
    return get_service().list_schemas()


@mcp.tool
def list_tables(schema_name: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
    """列出指定 Schema 下的表及其体量信息。"""
    return get_service().list_tables(schema_name=schema_name, limit=limit)


@mcp.tool
def execute_sql(
    sql_text: str,
    row_limit: int = 200,
    allow_mutation: bool = False,
) -> dict[str, Any]:
    """执行 SQL。默认仅允许只读语句；如需变更类 SQL，必须显式开启 allow_mutation。"""
    return get_service().execute_sql(
        sql_text=sql_text,
        row_limit=row_limit,
        allow_mutation=allow_mutation,
    )


@mcp.tool
def explain_sql(
    sql_text: str,
    mode: str = "auto",
    row_limit: int = 500,
    allow_mutation: bool = False,
) -> dict[str, Any]:
    """获取 SQL 执行计划，支持 auto/performance/analyze/basic 四种模式。"""
    return get_service().explain_sql(
        sql_text=sql_text,
        mode=mode,
        row_limit=row_limit,
        allow_mutation=allow_mutation,
    )


@mcp.tool
def get_table_ddl(schema_name: str, table_name: str) -> dict[str, Any]:
    """获取表 DDL，优先使用 pg_get_tabledef，失败时回退为拼装结果。"""
    return get_service().get_table_ddl(schema_name=schema_name, table_name=table_name)


@mcp.tool
def analyze_table_structure(schema_name: str, table_name: str) -> dict[str, Any]:
    """分析表结构、列定义、体量、统计信息和分布/分区线索。"""
    return get_service().analyze_table_structure(schema_name=schema_name, table_name=table_name)


@mcp.tool
def analyze_table_indexes(schema_name: str, table_name: str) -> dict[str, Any]:
    """分析索引定义、使用情况、疑似重复索引和低价值索引。"""
    return get_service().analyze_table_indexes(schema_name=schema_name, table_name=table_name)


@mcp.tool
def analyze_table_storage(schema_name: str, table_name: str) -> dict[str, Any]:
    """分析表空间碎片、脏页率、死元组比例和 VACUUM/ANALYZE 状态。"""
    return get_service().analyze_table_storage(schema_name=schema_name, table_name=table_name)


def main() -> None:
    mcp.run()

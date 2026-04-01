from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Optional

from .database import DwsDatabase, classify_sql
from .queries import (
    LIST_SCHEMAS_SQL,
    LIST_TABLES_SQL,
    PING_SQL,
    RESOLVE_TABLE_SQL,
    TABLE_COLUMNS_SQL,
    TABLE_DDL_SQL,
    TABLE_INDEXES_SQL,
    TABLE_STORAGE_DWS_DIRTY_SQL,
    TABLE_STORAGE_GLOBAL_SQL,
    TABLE_STORAGE_PGSTAT_SQL,
    TABLE_SUMMARY_SQL,
)


class DwsMcpService:
    def __init__(self, database: DwsDatabase) -> None:
        self.database = database

    def ping(self) -> dict[str, Any]:
        row = self.database.fetch_one(PING_SQL)
        return {
            "connection": "ok",
            "settings": self.database.settings.safe_summary(),
            "server": row or {},
        }

    def list_schemas(self) -> dict[str, Any]:
        schemas = self.database.fetch_all(LIST_SCHEMAS_SQL)
        return {"count": len(schemas), "schemas": schemas}

    def list_tables(
        self,
        schema_name: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        effective_limit = self.database.settings.clamp_row_limit(limit)
        tables = self.database.fetch_all(
            LIST_TABLES_SQL,
            (schema_name, schema_name, effective_limit),
        )
        return {
            "schema_name": schema_name,
            "limit": effective_limit,
            "count": len(tables),
            "tables": tables,
        }

    def execute_sql(
        self,
        sql_text: str,
        row_limit: Optional[int] = None,
        allow_mutation: bool = False,
    ) -> dict[str, Any]:
        return self.database.execute_sql(
            sql_text=sql_text,
            row_limit=row_limit,
            allow_mutation=allow_mutation,
        )

    def explain_sql(
        self,
        sql_text: str,
        mode: str = "auto",
        row_limit: Optional[int] = None,
        allow_mutation: bool = False,
    ) -> dict[str, Any]:
        classification = classify_sql(sql_text)
        requested_mode = (mode or "auto").strip().lower()
        if requested_mode not in {"auto", "performance", "analyze", "basic"}:
            raise ValueError("mode 仅支持 auto / performance / analyze / basic。")

        if classification["is_mutating"] and not (self.database.settings.allow_mutation and allow_mutation):
            raise ValueError(
                "为避免误执行写入类语句，变更 SQL 的计划分析必须同时开启环境级和调用级 allow_mutation。"
            )

        if requested_mode == "auto":
            if classification["is_mutating"]:
                candidates = [("basic", f"EXPLAIN {sql_text}")]
            else:
                candidates = [
                    ("performance", f"EXPLAIN PERFORMANCE {sql_text}"),
                    ("analyze", f"EXPLAIN ANALYZE {sql_text}"),
                    ("basic", f"EXPLAIN {sql_text}"),
                ]
        elif requested_mode == "performance":
            candidates = [("performance", f"EXPLAIN PERFORMANCE {sql_text}")]
        elif requested_mode == "analyze":
            candidates = [("analyze", f"EXPLAIN ANALYZE {sql_text}")]
        else:
            candidates = [("basic", f"EXPLAIN {sql_text}")]

        errors: list[dict[str, str]] = []
        for candidate_mode, statement in candidates:
            try:
                result = self.database.execute_sql(
                    statement,
                    row_limit=row_limit or 500,
                    allow_mutation=allow_mutation,
                )
                result["explain_mode"] = candidate_mode
                result["source_sql_type"] = classification["statement_type"]
                return result
            except Exception as exc:
                errors.append({"mode": candidate_mode, "error": str(exc)})

        raise RuntimeError({"message": "执行计划获取失败。", "attempts": errors})

    def get_table_ddl(self, schema_name: str, table_name: str) -> dict[str, Any]:
        table_meta = self._require_table(schema_name, table_name)
        ddl = self._try_get_table_ddl(table_meta["table_oid"])
        if ddl:
            return {
                "schema_name": schema_name,
                "table_name": table_name,
                "table_oid": table_meta["table_oid"],
                "source": "pg_get_tabledef",
                "table_ddl": ddl,
            }

        columns = self.database.fetch_all(TABLE_COLUMNS_SQL, (schema_name, table_name))
        return {
            "schema_name": schema_name,
            "table_name": table_name,
            "table_oid": table_meta["table_oid"],
            "source": "synthetic_fallback",
            "table_ddl": self._build_fallback_ddl(schema_name, table_name, columns),
        }

    def analyze_table_structure(self, schema_name: str, table_name: str) -> dict[str, Any]:
        table_meta = self._require_table(schema_name, table_name)
        summary = self.database.fetch_one(TABLE_SUMMARY_SQL, (table_meta["table_oid"],))
        columns = self.database.fetch_all(TABLE_COLUMNS_SQL, (schema_name, table_name))
        indexes = self.database.fetch_all(TABLE_INDEXES_SQL, (schema_name, table_name))
        ddl = self._try_get_table_ddl(table_meta["table_oid"])
        ddl_signals = self._parse_ddl_signals(ddl or "")

        recommendations: list[str] = []
        if summary and not summary.get("last_analyze") and not summary.get("last_autoanalyze"):
            recommendations.append("统计信息看起来未及时刷新，建议先执行 ANALYZE 再评估执行计划。")
        if summary and summary.get("estimated_rows", 0) and not indexes:
            recommendations.append("该表未发现索引，如为高选择性行存表，可进一步评估是否需要补充索引。")
        if not ddl:
            recommendations.append("当前集群可能不支持 pg_get_tabledef，DDL 为回退拼装结果，表选项可能不完整。")

        return {
            "schema_name": schema_name,
            "table_name": table_name,
            "table_oid": table_meta["table_oid"],
            "summary": summary,
            "storage_signals": ddl_signals,
            "columns": columns,
            "index_overview": {
                "count": len(indexes),
                "names": [item["index_name"] for item in indexes],
            },
            "ddl": ddl or self._build_fallback_ddl(schema_name, table_name, columns),
            "recommendations": recommendations,
        }

    def analyze_table_indexes(self, schema_name: str, table_name: str) -> dict[str, Any]:
        table_meta = self._require_table(schema_name, table_name)
        summary = self.database.fetch_one(TABLE_SUMMARY_SQL, (table_meta["table_oid"],))
        indexes = self.database.fetch_all(TABLE_INDEXES_SQL, (schema_name, table_name))

        issues: list[dict[str, Any]] = []
        duplicate_candidates: dict[str, list[str]] = defaultdict(list)
        for index in indexes:
            normalized = self._normalize_index_definition(index["index_definition"])
            duplicate_candidates[normalized].append(index["index_name"])

            index_bytes = index.get("index_bytes") or 0
            idx_scan = index.get("idx_scan") or 0
            is_primary = bool(index.get("is_primary"))
            is_unique = bool(index.get("is_unique"))
            is_valid = bool(index.get("is_valid"))
            is_ready = bool(index.get("is_ready"))

            if not is_valid or not is_ready:
                issues.append(
                    {
                        "index_name": index["index_name"],
                        "severity": "high",
                        "finding": "索引状态异常",
                        "detail": "索引未处于 valid/ready 状态，可能无法被优化器稳定使用。",
                    }
                )

            if idx_scan == 0 and not is_primary and not is_unique:
                issues.append(
                    {
                        "index_name": index["index_name"],
                        "severity": "medium",
                        "finding": "疑似长期未使用索引",
                        "detail": "idx_scan=0，且不是主键/唯一索引，建议结合业务窗口确认后再决定是否保留。",
                    }
                )

            if index_bytes >= 512 * 1024 * 1024 and idx_scan <= 10 and not is_primary:
                issues.append(
                    {
                        "index_name": index["index_name"],
                        "severity": "medium",
                        "finding": "大索引低使用",
                        "detail": "索引体量较大但扫描次数较低，可能带来维护成本而收益有限。",
                    }
                )

        for normalized, names in duplicate_candidates.items():
            if normalized and len(names) > 1:
                issues.append(
                    {
                        "index_name": ", ".join(names),
                        "severity": "medium",
                        "finding": "疑似重复索引",
                        "detail": "多个索引的定义核心片段一致，建议进一步核对是否存在重复维护。",
                    }
                )

        recommendations: list[str] = []
        if not indexes and summary and (summary.get("estimated_rows") or 0) > 100000:
            recommendations.append("大表未发现索引，可结合慢 SQL 的过滤列和连接列评估索引设计。")
        if issues:
            recommendations.append("建议先处理 invalid/未就绪索引，再评估低价值和重复索引。")
        else:
            recommendations.append("当前索引未发现明显异常，后续可结合具体慢 SQL 再做命中率分析。")

        return {
            "schema_name": schema_name,
            "table_name": table_name,
            "table_oid": table_meta["table_oid"],
            "table_summary": summary,
            "index_count": len(indexes),
            "indexes": indexes,
            "issues": issues,
            "recommendations": recommendations,
        }

    def analyze_table_storage(self, schema_name: str, table_name: str) -> dict[str, Any]:
        table_meta = self._require_table(schema_name, table_name)
        summary = self.database.fetch_one(TABLE_SUMMARY_SQL, (table_meta["table_oid"],))

        source = "pg_stat_user_tables"
        storage_rows: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        candidates = [
            ("pgxc_stat_table_dirty", TABLE_STORAGE_DWS_DIRTY_SQL),
            ("global_table_stat", TABLE_STORAGE_GLOBAL_SQL),
            ("pg_stat_user_tables", TABLE_STORAGE_PGSTAT_SQL),
        ]
        for source_name, sql_text in candidates:
            try:
                storage_rows = self.database.fetch_all(sql_text, (schema_name, table_name))
                source = source_name
                if storage_rows:
                    break
            except Exception as exc:
                errors.append({"source": source_name, "error": str(exc)})

        total_live = sum((row.get("n_live_tup") or 0) for row in storage_rows)
        total_dead = sum((row.get("n_dead_tup") or 0) for row in storage_rows)
        dead_tuple_ratio = 0.0
        if total_live + total_dead > 0:
            dead_tuple_ratio = round(total_dead * 100.0 / (total_live + total_dead), 2)

        dirty_rates = [row.get("dirty_page_rate") for row in storage_rows if row.get("dirty_page_rate") is not None]
        avg_dirty_rate = round(sum(dirty_rates) / len(dirty_rates), 2) if dirty_rates else None
        max_dirty_rate = round(max(dirty_rates), 2) if dirty_rates else None

        risk_level = "low"
        if (max_dirty_rate is not None and max_dirty_rate >= 80) or dead_tuple_ratio >= 30:
            risk_level = "high"
        elif (max_dirty_rate is not None and max_dirty_rate >= 50) or dead_tuple_ratio >= 15:
            risk_level = "medium"

        recommendations: list[str] = []
        if max_dirty_rate is not None and max_dirty_rate >= 50:
            recommendations.append("脏页率偏高，建议结合业务低峰评估 VACUUM 或重整窗口。")
        if dead_tuple_ratio >= 15:
            recommendations.append("死元组比例偏高，建议检查频繁更新/删除场景，并评估 VACUUM / ANALYZE 频率。")
        if not recommendations:
            recommendations.append("当前未发现明显空间碎片风险，可继续结合热点 SQL 和写入模式观察。")

        return {
            "schema_name": schema_name,
            "table_name": table_name,
            "table_oid": table_meta["table_oid"],
            "table_summary": summary,
            "stats_source": source,
            "storage_stats": storage_rows,
            "dead_tuple_ratio": dead_tuple_ratio,
            "avg_dirty_page_rate": avg_dirty_rate,
            "max_dirty_page_rate": max_dirty_rate,
            "risk_level": risk_level,
            "recommendations": recommendations,
            "fallback_errors": errors,
        }

    def _require_table(self, schema_name: str, table_name: str) -> dict[str, Any]:
        row = self.database.fetch_one(RESOLVE_TABLE_SQL, (schema_name, table_name))
        if row is None:
            raise ValueError(f"未找到对象：{schema_name}.{table_name}")
        return row

    def _try_get_table_ddl(self, table_oid: int) -> Optional[str]:
        try:
            row = self.database.fetch_one(TABLE_DDL_SQL, (table_oid,))
        except Exception:
            return None
        if not row:
            return None
        return row.get("table_ddl")

    def _build_fallback_ddl(
        self,
        schema_name: str,
        table_name: str,
        columns: list[dict[str, Any]],
    ) -> str:
        column_lines = []
        for column in columns:
            parts = [
                self._quote_ident(column["column_name"]),
                column["udt_name"] or column["data_type"],
            ]
            if column.get("column_default"):
                parts.append(f"DEFAULT {column['column_default']}")
            if column.get("is_nullable") == "NO":
                parts.append("NOT NULL")
            column_lines.append("    " + " ".join(parts))

        joined = ",\n".join(column_lines) if column_lines else "    -- 无法读取列定义"
        return (
            f"CREATE TABLE {self._quote_ident(schema_name)}.{self._quote_ident(table_name)} (\n"
            f"{joined}\n"
            ");"
        )

    def _parse_ddl_signals(self, ddl: str) -> dict[str, Any]:
        orientation_match = re.search(r"orientation\s*=\s*([a-zA-Z_]+)", ddl, flags=re.IGNORECASE)
        distribute_match = re.search(
            r"DISTRIBUTE\s+BY\s+([A-Z_]+)(?:\s*\((.*?)\))?",
            ddl,
            flags=re.IGNORECASE | re.DOTALL,
        )
        partitioned = bool(re.search(r"\bPARTITION\s+BY\b", ddl, flags=re.IGNORECASE))

        distribution_columns: list[str] = []
        distribution_type = None
        if distribute_match:
            distribution_type = distribute_match.group(1).upper()
            raw_columns = distribute_match.group(2) or ""
            distribution_columns = [
                item.strip().strip('"')
                for item in raw_columns.split(",")
                if item.strip()
            ]

        return {
            "orientation": orientation_match.group(1).lower() if orientation_match else None,
            "distribution_type": distribution_type,
            "distribution_columns": distribution_columns,
            "is_partitioned": partitioned,
        }

    def _normalize_index_definition(self, index_definition: Optional[str]) -> str:
        if not index_definition:
            return ""
        normalized = re.sub(
            r"^CREATE\s+(?:UNIQUE\s+)?INDEX\s+\S+\s+ON\s+\S+\s+",
            "",
            index_definition.strip(),
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.lower()

    def _quote_ident(self, name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

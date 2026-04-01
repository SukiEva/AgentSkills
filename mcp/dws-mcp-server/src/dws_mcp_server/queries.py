from __future__ import annotations

LIST_SCHEMAS_SQL = """
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name NOT IN ('information_schema')
  AND schema_name NOT LIKE 'pg_%'
ORDER BY schema_name;
"""

LIST_TABLES_SQL = """
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned_table'
        WHEN 'm' THEN 'materialized_view'
        ELSE c.relkind::text
    END AS table_kind,
    c.reltuples::bigint AS estimated_rows,
    pg_total_relation_size(c.oid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size_pretty
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'm')
  AND (%s IS NULL OR n.nspname = %s)
  AND n.nspname NOT IN ('information_schema')
  AND n.nspname NOT LIKE 'pg_%'
ORDER BY pg_total_relation_size(c.oid) DESC, n.nspname, c.relname
LIMIT %s;
"""

PING_SQL = """
SELECT
    current_database() AS current_database,
    current_user AS current_user,
    version() AS version,
    current_schema() AS current_schema,
    now() AS server_time;
"""

RESOLVE_TABLE_SQL = """
SELECT
    c.oid AS table_oid,
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relkind AS relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s
  AND c.relname = %s
  AND c.relkind IN ('r', 'p', 'm')
LIMIT 1;
"""

TABLE_SUMMARY_SQL = """
SELECT
    c.oid AS table_oid,
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relkind AS relkind,
    obj_description(c.oid, 'pg_class') AS table_comment,
    c.reltuples::bigint AS estimated_rows,
    pg_total_relation_size(c.oid) AS total_bytes,
    pg_relation_size(c.oid) AS table_bytes,
    pg_indexes_size(c.oid) AS index_bytes,
    GREATEST(pg_total_relation_size(c.oid) - pg_relation_size(c.oid) - pg_indexes_size(c.oid), 0) AS extra_bytes,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size_pretty,
    pg_size_pretty(pg_relation_size(c.oid)) AS table_size_pretty,
    pg_size_pretty(pg_indexes_size(c.oid)) AS index_size_pretty,
    COALESCE(s.seq_scan, 0) AS seq_scan,
    COALESCE(s.seq_tup_read, 0) AS seq_tup_read,
    COALESCE(s.idx_scan, 0) AS idx_scan,
    COALESCE(s.idx_tup_fetch, 0) AS idx_tup_fetch,
    COALESCE(s.n_live_tup, 0) AS n_live_tup,
    COALESCE(s.n_dead_tup, 0) AS n_dead_tup,
    s.last_vacuum,
    s.last_autovacuum,
    s.last_analyze,
    s.last_autoanalyze,
    s.vacuum_count,
    s.autovacuum_count,
    s.analyze_count,
    s.autoanalyze_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s
  ON s.schemaname = n.nspname
 AND s.relname = c.relname
WHERE c.oid = %s;
"""

TABLE_COLUMNS_SQL = """
SELECT
    cols.ordinal_position,
    cols.column_name,
    cols.data_type,
    cols.udt_name,
    cols.is_nullable,
    cols.column_default,
    cols.character_maximum_length,
    cols.numeric_precision,
    cols.numeric_scale,
    attr.attstattarget AS stat_target,
    st.null_frac,
    st.n_distinct,
    st.avg_width,
    pg_catalog.col_description(cls.oid, attr.attnum) AS column_comment
FROM information_schema.columns cols
JOIN pg_namespace ns
  ON ns.nspname = cols.table_schema
JOIN pg_class cls
  ON cls.relnamespace = ns.oid
 AND cls.relname = cols.table_name
JOIN pg_attribute attr
  ON attr.attrelid = cls.oid
 AND attr.attname = cols.column_name
 AND attr.attnum > 0
LEFT JOIN pg_stats st
  ON st.schemaname = cols.table_schema
 AND st.tablename = cols.table_name
 AND st.attname = cols.column_name
WHERE cols.table_schema = %s
  AND cols.table_name = %s
ORDER BY cols.ordinal_position;
"""

TABLE_INDEXES_SQL = """
SELECT
    idx.indexname AS index_name,
    idx.indexdef AS index_definition,
    pg_relation_size(ic.oid) AS index_bytes,
    pg_size_pretty(pg_relation_size(ic.oid)) AS index_size_pretty,
    am.amname AS access_method,
    i.indisprimary AS is_primary,
    i.indisunique AS is_unique,
    i.indisvalid AS is_valid,
    i.indisready AS is_ready,
    COALESCE(psui.idx_scan, 0) AS idx_scan,
    COALESCE(psui.idx_tup_read, 0) AS idx_tup_read,
    COALESCE(psui.idx_tup_fetch, 0) AS idx_tup_fetch,
    COALESCE(psaio.idx_blks_read, 0) AS idx_blks_read,
    COALESCE(psaio.idx_blks_hit, 0) AS idx_blks_hit,
    COALESCE(pg_get_expr(i.indpred, i.indrelid), '') AS predicate_expression,
    COALESCE(pg_get_expr(i.indexprs, i.indrelid), '') AS key_expression
FROM pg_indexes idx
JOIN pg_namespace ns
  ON ns.nspname = idx.schemaname
JOIN pg_class tc
  ON tc.relnamespace = ns.oid
 AND tc.relname = idx.tablename
JOIN pg_class ic
  ON ic.relname = idx.indexname
 AND ic.relnamespace = ns.oid
JOIN pg_index i
  ON i.indexrelid = ic.oid
JOIN pg_am am
  ON am.oid = ic.relam
LEFT JOIN pg_stat_user_indexes psui
  ON psui.schemaname = idx.schemaname
 AND psui.relname = idx.tablename
 AND psui.indexrelname = idx.indexname
LEFT JOIN pg_statio_all_indexes psaio
  ON psaio.schemaname = idx.schemaname
 AND psaio.relname = idx.tablename
 AND psaio.indexrelname = idx.indexname
WHERE idx.schemaname = %s
  AND idx.tablename = %s
ORDER BY pg_relation_size(ic.oid) DESC, idx.indexname;
"""

TABLE_DDL_SQL = "SELECT pg_get_tabledef(%s::oid) AS table_ddl;"

TABLE_STORAGE_DWS_DIRTY_SQL = """
SELECT
    schemaname AS schema_name,
    relname AS table_name,
    n_live_tup,
    n_dead_tup,
    dirty_page_rate,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count,
    analyze_count,
    autoanalyze_count
FROM pgxc_stat_table_dirty
WHERE schemaname = %s
  AND relname = %s
ORDER BY dirty_page_rate DESC;
"""

TABLE_STORAGE_GLOBAL_SQL = """
SELECT
    schemaname AS schema_name,
    relname AS table_name,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count,
    analyze_count,
    autoanalyze_count
FROM global_table_stat
WHERE schemaname = %s
  AND relname = %s;
"""

TABLE_STORAGE_PGSTAT_SQL = """
SELECT
    schemaname AS schema_name,
    relname AS table_name,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname = %s
  AND relname = %s;
"""

# DWS metadata SQL snippets (MCP)

以下模板用于 MCP 执行 SQL 时快速补齐证据。按实际版本/权限做字段兼容调整。

## 1) 表定义 / 存储方式

```sql
SELECT
  n.nspname      AS schema_name,
  c.relname      AS table_name,
  c.relkind      AS relkind,
  pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :schema
  AND c.relname = :table;
```

## 2) 索引定义（含列顺序）

```sql
SELECT
  schemaname,
  tablename,
  indexname,
  indexdef
FROM pg_indexes
WHERE schemaname = :schema
  AND tablename = :table
ORDER BY indexname;
```

## 3) 统计信息（表级）

```sql
SELECT
  schemaname,
  relname,
  n_live_tup,
  n_dead_tup,
  last_analyze,
  last_autoanalyze
FROM pg_stat_all_tables
WHERE schemaname = :schema
  AND relname = :table;
```

## 4) 统计信息（列级）

```sql
SELECT
  schemaname,
  tablename,
  attname,
  null_frac,
  n_distinct
FROM pg_stats
WHERE schemaname = :schema
  AND tablename = :table;
```

## 5) 计划验证优先级

```sql
EXPLAIN PERFORMANCE <sql>;
-- fallback:
EXPLAIN ANALYZE <sql>;
-- fallback:
EXPLAIN <sql>;
```

## 6) 分布/倾斜验证（示例）

```sql
SELECT table_skewness(':schema.:table');
```

> 备注：若集群未启用该函数，改为按分布列分组统计热点值占比。

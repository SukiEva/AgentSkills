# Output blueprint

按下面模板组织回复。

```markdown
## DWS 慢 SQL 分析结论

### 1. 一句话结论
- ...

### 2. 关键信息
- SQL 类型：...
- 执行计划类型：EXPLAIN / EXPLAIN ANALYZE / EXPLAIN PERFORMANCE
- 总耗时：...
- 最重节点：...
- 是否存在分布式传输：有 / 无
- 是否怀疑数据倾斜：高 / 中 / 低

### 3. 慢 SQL 根因
1. 根因标题
   - 证据：...
   - 影响：...
   - 判断性质：确定 / 高概率推断

### 4. 优化建议（按优先级排序）
1. [高] ...
   - 原因：...
   - SQL：...
   - 预期收益：...
   - 风险/代价：...
   - 验证方式：...

### 5. 立即可执行的下一步
- ...

### 6. 建议补充的信息
- ...
```

## SQL templates

### 1. 更新统计信息

```sql
ANALYZE schema.table;
```

### 2. 检查数据倾斜

```sql
SELECT table_skewness('schema.table');
```

### 3. 行存表复合索引模板

适用前提：行存表、高选择性过滤、热点 SQL 高频执行、瓶颈来自扫描或排序。

```sql
CREATE INDEX idx_<table>_<col1>_<col2>
ON schema.table (equal_filter_col, join_or_order_col);
```

字段顺序规则：
1. 等值过滤列优先。
2. 高频 JOIN 列其次。
3. 排序列放最后。

验证动作建议：

```sql
EXPLAIN PERFORMANCE <optimized_sql>;
```

### 4. 重分布/重建模板

适用前提：核心瓶颈是 `REDISTRIBUTE`、`BROADCAST`、`GATHER` 或严重倾斜。

```sql
CREATE TABLE schema.table_new
WITH (ORIENTATION = COLUMN)
AS
SELECT *
FROM schema.table
DISTRIBUTE BY HASH (new_dist_key);
```

提示：如果用户未提供完整 DDL，只输出模板并标注“需确认表属性、主键、压缩、分区定义”。

### 5. 安全 SQL rewrite checklist

只优先给出以下低风险改写：
- 尽早过滤。
- 去掉无必要的 `SELECT *`。
- 修复过滤列函数包裹。
- 修复隐式类型转换。
- 避免重复排序或重复去重。

如果可能改变结果集语义，必须标注：`需业务确认`。

## Verification checklist

给出建议后，默认补一条验证方案：

1. 看执行计划中最重节点是否变化。
2. 看 `REDISTRIBUTE` / `BROADCAST` / `GATHER` 是否减少。
3. 看扫描行数、排序输入行数是否下降。
4. 看总耗时是否改善。
5. 如果是索引方案，看写入代价是否可接受。

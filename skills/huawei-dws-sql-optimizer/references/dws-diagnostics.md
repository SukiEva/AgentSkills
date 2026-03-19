# DWS diagnostics map

在判断根因时，优先将症状映射到以下类型。

## 1. Distributed / MPP symptoms

### `Streaming (type: REDISTRIBUTE)`
- 含义：JOIN、GROUP BY、ORDER BY 所需数据不在相同分布上。
- 证据：Streaming 节点耗时高、行数大、网络传输量大。
- 首选动作：
  1. 检查 JOIN 键是否与分布键一致。
  2. 检查是否可以改成 colocated join。
  3. 如果是核心大表，优先建议重建表分布。
- 不要默认动作：直接建议加索引。

### `Streaming (type: BROADCAST)`
- 含义：将一张表广播到多个 DN。
- 什么时候正常：小维表、结果集很小。
- 什么时候危险：被广播对象并不小、统计信息错误导致优化器误判。
- 首选动作：
  1. 更新统计信息。
  2. 检查维表是否真的小。
  3. 如果两边都是大表，考虑调整分布键以避免广播。

### `Streaming (type: GATHER)`
- 含义：数据回流到 CN。
- 风险：大结果集聚集到 CN，网络与单点 CPU 成为瓶颈。
- 首选动作：
  1. 尽量在 DN 端先过滤、聚合、去重。
  2. 减少返回列与返回行数。
  3. 避免无必要的全局排序。

## 2. Data skew symptoms

### DN 时间差异明显
- 含义：不同 DN 处理负载不均。
- 证据：某一 DN time/rows 明显高于其他 DN。
- 首选动作：
  1. 执行 `SELECT table_skewness('schema.table');`
  2. 检查分布键是否低基数、热点值集中、时间类字段偏斜。
  3. 必要时建议更换分布键或通过 CTAS 重建表。

## 3. Scan symptoms

### `Seq Scan` / `CStore Scan` 大扫描
- 含义：读取数据远大于最终返回数据。
- 常见原因：
  - 缺索引（行存表）
  - 谓词不可下推
  - 分区未裁剪
  - 过滤列上有函数或隐式类型转换
- 首选动作：
  1. 先检查谓词是否可改写为 SARGable。
  2. 再检查分区键是否命中。
  3. 对行存且高选择性条件，再考虑复合索引。

## 4. Join symptoms

### 大表对大表 `Nested Loop`
- 通常不是最优策略。
- 先确认：
  1. JOIN 之前是否已经过滤。
  2. JOIN 两侧数据类型是否一致。
  3. JOIN 键是否导致重分布。
- 首选动作：
  1. 让过滤条件尽早下推。
  2. 让 JOIN 键与分布键匹配。
  3. 对小表探测大表且行存场景，再考虑索引。

## 5. Aggregate / Sort symptoms

### `Sort` / `HashAggregate` / `Aggregate`
- 风险：排序、去重、聚合前数据量太大。
- 首选动作：
  1. 先减少输入行数。
  2. 先局部聚合后汇总。
  3. 对高选择性行存查询，考虑与过滤、排序一致的复合索引。

## 6. Statistics symptoms

### 估算行数与实际行数差异大
- 影响：连接顺序、广播与重分布决策失真。
- 首选动作：

```sql
ANALYZE schema.table;
```

- 说明：如果只是统计信息不准，不要直接把“建索引”作为唯一答案。

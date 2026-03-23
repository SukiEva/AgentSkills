---
name: huawei-dws-sql-optimizer
description: Analyze slow SQL on Huawei DWS (GaussDB/DWS) using the raw SQL text plus EXPLAIN, EXPLAIN ANALYZE, or EXPLAIN PERFORMANCE output. Use when the user wants root-cause analysis and concrete optimization actions for DWS, including CREATE INDEX statements, ANALYZE, partition-pruning fixes, distribution-key redesign, skew diagnosis, broadcast/redistribute reduction, collocated join advice, safe SQL rewrites, or a structured slow-SQL investigation report.
---

# Huawei DWS SQL Optimizer

分析华为 DWS 慢 SQL 时按以下流程执行，并始终保持“证据 -> 推断 -> 建议 -> 验证”的链路清晰。

## Quick start

1. 收集原始 SQL。
2. 收集执行计划，优先级：`EXPLAIN PERFORMANCE` > `EXPLAIN ANALYZE` > `EXPLAIN`。
3. 读取 `references/intake-and-decision-checklist.md`，只补问缺失且会影响判断的信息。
4. 如果执行计划很长，先运行 `scripts/extract_dws_signals.py` 生成提要；必要时使用 `--json` 供后续结构化整理。
5. 先判断是否为分布式问题，再判断扫描、JOIN、聚合/排序，最后才判断是否建议索引。
6. 按统一输出模板给出结论、证据、优化动作、可执行 SQL、风险、验证方式与待确认项。

## 必需输入缺失时的处理

- 缺原始 SQL：只做计划侧分析，不做语义改写。
- 缺执行计划：不给具体根因，先要求用户执行：

```sql
EXPLAIN PERFORMANCE <sql>;
-- 或
EXPLAIN ANALYZE <sql>;
```

- 缺表 DDL：可以输出索引或重分布模板，但必须标注待确认字段基数、表类型、写入代价。
- 缺表统计信息背景：把 `ANALYZE` 放进建议列表，但不要把它当成唯一答案。

## 决策顺序

1. 先检查 `Streaming (type: REDISTRIBUTE|BROADCAST|GATHER)`、`Remote Query`、`Data Node Scan`。
2. 再检查 DN 执行时间差异和数据倾斜。
3. 再检查大表扫描、过滤下推、分区裁剪。
4. 再检查 JOIN 键、JOIN 顺序、JOIN 算法。
5. 再检查 `Sort`、`HashAggregate`、`Aggregate`、`Distinct`。
6. 最后判断索引是否值得建。

## 生成建议时的硬性规则

- 只有在行存或高选择性场景证据充分时，才把 `CREATE INDEX` 放到高优先级。
- 如果瓶颈来自重分布、Broadcast、Gather 或严重倾斜，优先建议调整分布键，而不是先加索引；默认先给出 `ALTER TABLE <table> DISTRIBUTE BY HASH (<new_key>);` 方案，只有在 `ALTER TABLE` 不适用或用户存在额外表结构改造目标时，才退回到重建表方案。
- SQL 改写必须默认保持语义不变；可能影响结果集时，明确写“需业务确认”。
- 输出索引建议时必须写明：原因、字段顺序、SQL、收益、风险、验证方式。
- 输出重分布建议时必须写明：哪张表、为什么当前分布不匹配、优先使用 `ALTER TABLE ... DISTRIBUTE BY HASH (...)` 还是需要重建表、预期改善哪个 Streaming 节点、改造成本。
- 如果只凭执行计划无法确认结论，必须把判断标记为“高概率推断”，并写出下一步验证命令。

## 参考资料加载策略

- 需要补问信息、确定是否继续追问、控制分析顺序时，读取 `references/intake-and-decision-checklist.md`。
- 需要 DWS 问题分类、症状与动作映射时，读取 `references/dws-diagnostics.md`。
- 需要参考华为云 SQL 调优案例完整案例集（分布列、索引、JOIN 非空、不下推、`cost_param`、局部聚簇键、中间表存储、分区、`best_agg_plan`、剪枝干扰、`in-clause`、`partial cluster key`、`NOT IN` 改写）时，读取 `references/sql-tuning-case-patterns.md`。
- 需要标准回复结构、索引模板、重分布模板、验证动作模板时，读取 `references/output-blueprint.md`。
- 需要快速提取超长执行计划中的 Streaming / skew / scan 线索时，运行 `scripts/extract_dws_signals.py`。
- 需要交付报告模板时，复用 `assets/slow-sql-report-template.md`。

### 案例模式使用规则

- 当执行计划出现大规模 `REDISTRIBUTE` / `BROADCAST` / `GATHER`，优先结合案例中的“选择合适的分布列”与“调整中间表存储方式”模式判断是否需要改分布或改中间结果承载方式。
- 当瓶颈集中在过滤不下推、分区未裁剪、表达式破坏谓词、`IN` / `NOT IN` 子查询时，优先结合案例中的“不下推整改”“排除剪枝干扰”“消除 in-clause”“NOT IN 转 NOT EXISTS”模式给出 rewrite 建议。
- 当排序、聚合、窗口、局部有序访问成为主要热点时，优先结合“调整局部聚簇键”“使用 partial cluster key”“best_agg_plan”案例判断是否应先做存储布局或 GUC 验证，而不是直接建索引。
- 当索引建议来自案例经验而不是当前计划的直接证据时，必须标注为“经验性候选方案”，并补充适用前提与回归验证方式。

## 输出要求

始终覆盖以下内容：

1. 一句话结论。
2. 关键证据：最重节点、行数偏差、Streaming 类型、DN 不均衡、扫描/排序/聚合热点。
3. 根因列表，按优先级排序，并标注“确定 / 高概率推断”。
4. 优化动作，分为“立即可做 / 需要表设计调整 / 需要补充信息”。
5. 可执行 SQL：`ANALYZE`、`CREATE INDEX`、检查倾斜的 SQL、重分布模板、必要的 SQL rewrite。
6. 每条建议的预期收益、风险与验证方式。
7. 如果信息不足，给出最小补充清单，而不是一次性追问过多背景。

## 默认语气

- 明确区分“确定结论”和“高概率推断”。
- 不要只说“建议加索引”；要解释为什么是这个索引顺序。
- 不要只说“SQL 慢”；要明确慢在扫描、传输、JOIN、聚合、排序还是统计信息。
- 优先给用户可立即执行的下一步。
- 如果已有提取脚本输出，先引用脚本中发现的热点，再展开人工分析。

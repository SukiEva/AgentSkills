---
name: huawei-dws-sql-optimizer
description: Analyze and optimize slow SQL on Huawei DWS (GaussDB/DWS) with an evidence-first workflow. Proactively use MCP to collect schema/index/statistics/distribution metadata and validate plans (EXPLAIN PERFORMANCE/ANALYZE/EXPLAIN), then provide root-cause analysis, prioritized actions, executable SQL, risk notes, and verification steps.
---

# Huawei DWS SQL Optimizer

分析华为 DWS 慢 SQL 时按以下流程执行，并始终保持“证据 -> 推断 -> 建议 -> 验证”的链路清晰。

## 适用范围

### 适用

- 用户要分析 DWS/GaussDB 慢 SQL 根因并拿到可执行优化动作；
- 用户已有 SQL 或执行计划，希望快速给出优先级建议；
- 用户需要结构化慢 SQL 报告（结论、证据、动作、风险、验证）。

### 不适用（需先澄清）

- 非 DWS/GaussDB 方言或纯应用层瓶颈（网络、连接池、并发限流）；
- 用户只要“泛泛调优建议”且不提供 SQL/计划；
- 需要直接执行高风险 DDL/DML（本技能默认只读分析 + `EXPLAIN*` 验证）。

## Quick start（7 步）

1. 收集原始 SQL（无 SQL 时仅做方法级建议）。
2. 探测 MCP 是否可用；可用则先自主取证，不可用再向用户索取。
3. 获取执行计划，优先级：`EXPLAIN PERFORMANCE` > `EXPLAIN ANALYZE` > `EXPLAIN`。
4. 读取 `references/intake-and-decision-checklist.md`，仅补问会阻断判断的缺口。
5. 执行计划过长时运行 `scripts/extract_dws_signals.py` 先抽取热点。
6. 按“分布式传输 -> 倾斜 -> 扫描过滤 -> JOIN -> 聚合排序 -> 索引”顺序分析。
7. 按 `references/output-blueprint.md` 输出：结论、证据、动作、SQL、风险、验证、待确认项。

## 执行模式选择

- **Mode A（MCP-first）**：能访问 MCP 时默认使用。先自主取证，再最小补问。
- **Mode B（User-evidence）**：MCP 不可用时，基于用户提供 SQL/计划/DDL 分析。
- **Mode C（Plan-only）**：仅有执行计划时，允许输出“高概率推断”，但必须附最小补充清单。

## MCP 自主探查模式（默认启用）

当 MCP 可用时，必须先走“自主取证”再决定是否追问用户。

### A. 资源发现

1. 使用 MCP 资源发现能力列出可用资源/模板。
2. 优先选择与 DWS / GaussDB / PostgreSQL 系统目录、SQL 执行、执行计划相关的资源。
3. 若存在多个连接，默认选择与用户 SQL 所在库最匹配的连接（库名/Schema/方言最接近）。

### B. 元数据取证

对 SQL 涉及对象按需收集：

- 表/视图 DDL；
- 索引定义（列顺序、类型、可用状态）；
- 分布键、分区定义、存储方式（行存/列存）；
- 统计信息（行数估计、统计时间、列基数信息）。

优先复用 `references/dws-metadata-sql-snippets.md` 的查询模板。

### C. 执行计划验证

对“原 SQL”先执行：`EXPLAIN PERFORMANCE`；失败再降级：

1. `EXPLAIN ANALYZE`
2. `EXPLAIN`

如果给出 rewrite，必须用 `EXPLAIN*` 对比“原 SQL vs rewrite SQL”，禁止直接执行真实 DML 验证。

### D. 失败降级与补问

遇到权限/连接/对象缺失时，按固定格式输出：

- 缺失项（具体到对象/字段）；
- 对结论影响（哪些结论降级为“高概率推断”）；
- 最小补充清单（最多 3 条，且可直接执行）。

### E. 安全边界（强约束）

- 禁止执行任何改写业务数据的语句；
- 禁止执行不可逆 DDL；
- 默认只读 + `EXPLAIN*`；
- 所有 MCP 拉取内容需在结果中标记“已验证证据（MCP）”。

## 输出质量门槛（必须满足）

1. 每个根因必须有证据，不允许“无证据结论”。
2. 每条建议必须给“收益 + 风险 + 验证动作”。
3. 至少给 1 条可立即执行的低风险动作（例如 `ANALYZE`、`EXPLAIN*` 对比、SARGable rewrite）。
4. 涉及语义变化的 rewrite 必须标注“需业务确认”。
5. 结论必须区分“确定”与“高概率推断”。

## 调优实验闭环（新增）

每次优化都按“基线 -> 变更 -> 复测 -> 回滚预案”输出：

1. 基线：记录原 SQL 的总耗时、最重节点、扫描行数、Streaming 开销。
2. 变更：每次只改一类变量（索引 / 分布键 / rewrite / 参数），避免多变量混改。
3. 复测：至少执行一次 `EXPLAIN*` 对比，必要时做小流量真实压测。
4. 回滚：给出撤销语句或回退步骤（删索引、恢复参数、回切 SQL）。

## 常见 SQL 反模式速查（新增）

在建议 rewrite 前，优先检查以下反模式：

- `SELECT *` 导致无效列回传；
- 过滤列函数包裹，破坏下推/索引命中；
- 隐式类型转换导致计划偏差；
- 大 `IN (...)` / 深层子查询造成优化复杂度飙升；
- 可提前过滤却放在后置层（例如外层再过滤）。

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
- 需要按 MCP 自主探查数据库对象、索引与执行计划时，读取 `references/mcp-autodiscovery-playbook.md`。
- 需要系统表查询模板（DDL、索引、统计信息、分布/分区、计划验证）时，读取 `references/dws-metadata-sql-snippets.md`。
- 需要 DWS 问题分类、症状与动作映射时，读取 `references/dws-diagnostics.md`。
- 需要通用调优方法论（定位->改写->结构->参数）时，读取 `references/sql-tuning-methodology.md`。
- 需要 SQL 反模式与 rewrite 优先级建议时，读取 `references/sql-rewrite-anti-patterns.md`。
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
- 建议默认按“高 / 中 / 低”优先级分组，避免平铺罗列。

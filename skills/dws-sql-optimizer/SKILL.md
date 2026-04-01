---
name: dws-sql-optimizer
description: Analyze and optimize slow SQL on Huawei DWS / GaussDB(DWS). Default to a dws-mcp-server-first workflow: proactively use DWS MCP tools to execute EXPLAIN, inspect table DDL, columns, indexes, storage, and fragmentation before asking the user for more evidence. Use this when the user provides DWS SQL, execution plans, slow-query symptoms, or wants root-cause analysis plus actionable tuning steps.
---

# DWS SQL Optimizer

分析 DWS / GaussDB(DWS) 慢 SQL 时，默认走“`dws-mcp-server` 自主取证优先”流程，并始终保持“证据 -> 推断 -> 建议 -> 验证”的链路清晰。

## 适用范围

### 适用

- 用户要分析 DWS 慢 SQL 根因并拿到可执行优化动作；
- 用户提供了 SQL、表名、执行计划、慢查询现象中的任一项；
- 用户希望基于 DWS 元数据、索引、空间碎片、执行计划做结构化诊断；
- 用户要一份按优先级排序、可验证、可回滚的优化建议。

### 不适用

- 非 DWS / GaussDB(DWS) 方言；
- 问题明显是应用层瓶颈（连接池、网络、并发闸门），且没有数据库侧证据；
- 用户要求直接执行不可逆 DDL / DML，本技能默认不做高风险落地执行。

## 默认工作模式

- **Mode A: `dws-mcp-server` 优先**
  只要能访问 `dws-mcp-server`，就先自主诊断，不要一上来要求用户手工执行 SQL。
- **Mode B: 用户证据回退**
  `dws-mcp-server` 不可用、连接失败、权限不足时，基于用户提供的 SQL / 计划 / DDL 分析。
- **Mode C: 计划单独分析**
  只有执行计划时，允许输出“高概率推断”，但必须附最小补充清单。

## Quick start

1. 先确认问题对象：原始 SQL、目标表、异常现象三者至少拿到一个。
2. 默认先尝试 `dws-mcp-server`，不要先追问用户跑 `EXPLAIN`。
3. 优先获取计划、表结构、索引、表存储/碎片信息，再决定是否补问。
4. 按“分布式传输 -> 倾斜 -> 扫描过滤 -> JOIN -> 聚合排序 -> 索引/存储”顺序分析。
5. 输出时明确区分“已验证证据（dws-mcp-server）”和“高概率推断”。

## `dws-mcp-server` 优先诊断 SOP

只要 `dws-mcp-server` 可用，必须优先按下面顺序执行；除非用户明确禁止访问数据库，或该服务不可用。

### Step 1: 连接探活

先调用：

- `ping`

如果失败：

- 记录失败原因；
- 不要重复盲试过多次；
- 立即降级到用户证据模式，并明确告诉用户缺少什么连接条件。

### Step 2: 对象识别

如果用户只给 SQL：

1. 从 SQL 中提取关键对象；
2. 对未带 schema 的对象，必要时用 `list_tables` 辅助确认；
3. 控制对象范围，默认只分析前 5-10 个关键表。

如果用户只给表名或怀疑某张表有问题：

- 直接围绕该表拉取结构、索引、存储诊断。

### Step 3: 证据采集优先级

优先用高层工具，不要先写大量 catalog SQL：

1. `explain_sql`
2. `analyze_table_structure`
3. `analyze_table_indexes`
4. `analyze_table_storage`
5. `get_table_ddl`

只有在上述工具返回信息不足时，才使用：

- `execute_sql`
- `references/dws-metadata-sql-snippets.md`

### Step 4: 执行计划采集规则

对原 SQL 优先执行：

1. `explain_sql(mode="auto")`
2. 若用户明确要求某种模式，再指定 `performance / analyze / basic`

如果要比较 rewrite 或索引方案：

- 只能做 `EXPLAIN*` 对比；
- 不执行真实 DML 验证；
- 涉及写入语义的 SQL，默认只讨论风险和验证方式。

### Step 5: 结构与存储采集规则

对关键表至少尝试拿到：

- 表 DDL / 列定义；
- 行数估计、统计信息新鲜度；
- 索引定义、索引使用情况、疑似重复索引；
- 存储线索：行存/列存、分区、分布键；
- 空间碎片线索：脏页率、死元组比例、VACUUM / ANALYZE 状态。

### Step 6: 失败降级

当 `dws-mcp-server` 只能拿到部分证据时，输出必须包含三段：

1. 缺失项：具体缺了什么，例如执行计划、DDL、索引统计、碎片信息；
2. 影响：哪些结论只能降级为“高概率推断”；
3. 最小补充清单：最多 3 条，且必须是用户可直接执行或直接提供的内容。

## 分析顺序

1. 先看 `REDISTRIBUTE` / `BROADCAST` / `GATHER` / `Remote Query`。
2. 再看 DN 时间差异和数据倾斜。
3. 再看大表扫描、过滤下推、分区裁剪。
4. 再看 JOIN 键、JOIN 顺序、JOIN 算法。
5. 再看 `Sort` / `HashAggregate` / `Aggregate` / `Distinct`。
6. 最后看索引、统计信息、空间碎片是否放大了问题。

## 建议生成规则

- 没有证据时，不要给确定性结论。
- 索引建议必须写明字段顺序、适用前提、收益、代价、验证方式。
- 若瓶颈是重分布、Broadcast、Gather 或倾斜，优先考虑分布键和数据分布，不要先喊“加索引”。
- 当 `analyze_table_storage` 显示脏页率或死元组比例偏高时，要把空间碎片 / VACUUM 策略纳入根因链，而不是只盯 SQL 文本。
- SQL 改写默认保持语义不变；可能影响结果集时，明确标注“需业务确认”。
- 至少给 1 条低风险、可立即执行的下一步。

## 何时追问用户

只有满足以下任一条件时才追问，且单轮最多 3 条：

- `dws-mcp-server` 不可用或无权限；
- 原 SQL 缺失，且用户也未给表名或计划；
- 需要业务语义才能判断 rewrite 是否安全；
- 需要确认表改造窗口、写入代价、回滚约束。

不要在 `dws-mcp-server` 可用时先问用户去跑 `EXPLAIN` 或导 DDL。

## 输出要求

始终覆盖：

1. 一句话结论；
2. `dws-mcp-server` 取证摘要；
3. 根因列表，标注“确定 / 高概率推断”；
4. 优化动作，分为“立即可做 / 需要结构调整 / 需要补充信息”；
5. 可执行 SQL 或 `dws-mcp-server` 验证动作；
6. 每条建议的收益、风险、验证方式；
7. 回滚或回退思路。

## 参考资料加载策略

- 需要判断是否继续追问、控制补充信息范围时，读 `references/intake-and-decision-checklist.md`
- 需要按 `dws-mcp-server` 执行固定自主诊断流程时，读 `references/mcp-autodiscovery-playbook.md`
- 需要补写 catalog SQL 时，读 `references/dws-metadata-sql-snippets.md`
- 需要映射症状到根因分类时，读 `references/dws-diagnostics.md`
- 需要通用调优方法时，读 `references/sql-tuning-methodology.md`
- 需要判断 rewrite 风险时，读 `references/sql-rewrite-anti-patterns.md`
- 需要案例迁移时，读 `references/sql-tuning-case-patterns.md`
- 需要标准输出结构时，读 `references/output-blueprint.md`
- 执行计划过长时，运行 `scripts/extract_dws_signals.py`
- 需要交付报告模板时，复用 `assets/slow-sql-report-template.md`

## 默认语气

- 明确区分“已验证证据（dws-mcp-server）”与“高概率推断”。
- 不要只说“建议加索引”，要解释为什么是这个索引顺序。
- 不要只说“SQL 慢”，要明确慢在扫描、传输、JOIN、聚合、排序、统计信息还是空间碎片。
- 优先给用户可立即执行的下一步。

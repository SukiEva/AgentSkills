# dws-mcp-server autodiscovery playbook

用于在 `dws-mcp-server` 可用时把“慢 SQL 排查”升级为“自动取证 + 验证闭环”。

## 1) 目标与边界

- 目标：自动获取表结构、索引、分区/分布、统计信息、空间碎片与执行计划，减少人工追问。
- 边界：仅只读查询与 `EXPLAIN*` 验证；禁止写入数据、禁止不可逆 DDL。

## 2) 标准执行流程（SOP）

### Step A: 探活与能力确认

1. 先调用 `ping`。
2. 确认至少可用以下工具中的一部分：
   - `explain_sql`
   - `analyze_table_structure`
   - `analyze_table_indexes`
   - `analyze_table_storage`
   - `get_table_ddl`
   - `execute_sql`
3. 若服务已连接成功，默认直接进入自主诊断，不先追问用户执行 SQL。

### Step B: 解析 SQL 对象

1. 抽取 SQL 涉及对象：`schema.table`、视图、子查询中的核心表。
2. 建立对象清单（最多前 10 个关键对象，避免上下文污染）。

### Step C: 拉取元数据

对每个关键对象按优先级执行：

1. `analyze_table_structure`：拿列定义、体量、统计时间、分布/分区/存储线索；
2. `analyze_table_indexes`：拿索引定义、使用情况、疑似重复索引；
3. `analyze_table_storage`：拿死元组比例、脏页率、VACUUM / ANALYZE 状态；
4. `get_table_ddl`：在需要完整 DDL 或核对表属性时补充。

只有当工具结果不够时，才回退到 `execute_sql` + `references/dws-metadata-sql-snippets.md`。

### Step D: 执行计划与对比验证

1. 原 SQL：先 `explain_sql(mode="auto")`。
2. 候选优化 SQL：仅执行 `EXPLAIN*` 对比，不执行真实 DML。
3. 对比以下信号：
   - 最重节点是否变化；
   - `REDISTRIBUTE/BROADCAST/GATHER` 是否减少；
   - 扫描/排序/聚合输入行数是否下降；
   - 估算行数偏差是否收敛。

## 3) 证据分级（输出必须标注）

- A 级（强证据）：`dws-mcp-server` 直接返回的 plan、DDL、索引、统计快照、碎片快照。
- B 级（中证据）：由 A 级直接推导（如分布键错配导致重分布）。
- C 级（弱证据）：案例迁移/经验建议（必须附前提 + 验证动作）。

## 4) 失败降级策略（固定模板）

当 `dws-mcp-server` 无法完整提供数据时，必须输出三段：

1. 缺失项：例 `schema.foo` 分区定义不可见（权限不足）。
2. 影响：哪些结论降级为“高概率推断”。
3. 最小补充：最多 3 条、可直接执行的补充命令或输出要求。

## 5) 结果合成规则

每条建议必须包含：

- 证据来源（`dws-mcp-server` / 用户提供）；
- 预期收益（降低哪类节点开销）；
- 风险与代价（写入放大、改造窗口、回滚难度）；
- 验证动作（至少 1 条）。

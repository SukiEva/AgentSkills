---
name: oracle-plus-join-rewriter
description: Rewrite Oracle legacy outer join syntax that uses `(+)` into standard ANSI JOIN SQL, and convert comma-style joins to explicit INNER JOIN when that can be proven not to change the result set, while preserving unchanged text outside the rewritten join-related clauses. Use when the user provides Oracle SQL containing `(+)`, comma joins in `FROM`, wants a standards-compliant rewrite, wants only the necessary join-related edits, or needs a safety review for whether the rewrite could change the result set.
---

# Oracle Plus Join Rewriter

将 Oracle 旧式外连接条件 `(+)` 改写为 ANSI `JOIN ... ON ...` 时，严格执行以下规则。

## Quick start

1. 先定位所有包含 `(+)` 的谓词，以及 `FROM a, b, c` 这类逗号连接里可明确识别为连接关系的谓词。
2. 只围绕这些 join-related 片段改写；其余 SQL 保持原样：不要重排其他条件、不要格式化整段 SQL、不要改别名、不要改函数、不要改 hint。
3. 先判断每个 `(+)` 实际表达的是 `LEFT JOIN`、`RIGHT JOIN`，还是无法安全确定。
4. 再判断逗号连接中的普通等值连接是否可以在**不改变结果集**的前提下改为显式 `INNER JOIN`。
5. 检查 `WHERE` 中是否还有引用被外连接表或待改 inner join 表的过滤条件；若这些条件在改写后需要移入 `ON` 才能保留语义，必须明确说明原因。
6. 若改写可能改变结果集、去重、空值保留行为、过滤时机或连接顺序影响，先暂停并向用户确认，再给最终改写版本。
7. 输出时分成三部分：`改写后的 SQL`、`仅涉及改写的差异说明`、`是否需要业务确认`。

## Hard rules

- 只修改与 join 改写直接相关的部分。
- 不要顺手优化、清理、格式化或重构其它 SQL。
- 对于逗号连接，只有在能明确证明它就是普通内连接关系、且改成 `INNER JOIN` 不会改变结果集时，才允许改写。
- 不要把普通内连接条件改成 ANSI JOIN，除非它本身就是这次 join 标准化的一部分；若发生这种情况，要在差异说明中点明。
- 如果原 SQL 的写法本身有歧义、互相冲突，或存在 Oracle 专有语义难以无损表达，必须停止并说明原因。
- 如果无法 100% 确认结果集不变，明确标记为“需业务确认”，并列出触发风险的具体谓词。

## Rewrite workflow

### 1. Identify join groups

- 找出所有带 `(+)` 的比较谓词。
- 找出逗号连接表之间的普通 join 谓词，例如 `a.id = b.id`。
- 确认每个谓词两侧分别属于哪张表/别名。
- 将指向同一外连接表的一组谓词合并分析，避免拆成多个 JOIN 造成语义错误。

### 2. Infer join direction

使用以下经验规则：

- `a.col = b.col(+)` 通常改写为 `a LEFT JOIN b ON a.col = b.col`。
- `a.col(+) = b.col` 通常改写为 `a RIGHT JOIN b ON a.col = b.col`；若用户没有要求保留 `RIGHT JOIN`，优先等价改写为交换顺序后的 `LEFT JOIN`，但仅在不会影响其余文本稳定性时这样做。
- 多个针对同一外表的 `(+)` 谓词，必须一起进入同一个 `ON` 子句。

### 3. Convert safe comma joins to INNER JOIN

仅当以下条件同时满足时，才把逗号连接改成显式 `INNER JOIN`：

- 连接谓词是清晰的普通等值连接，如 `a.id = b.id`。
- 相关谓词不涉及 `(+)`、`OR`、函数包裹列、非等值比较或复杂布尔逻辑。
- 将该谓词从 `WHERE` 移入 `ON` 不会改变剩余过滤条件的语义。
- 不需要重排大量 `FROM` 结构，也不需要顺带改写无关表之间的关系。

若满足以上条件，优先把与 `(+)` 改写相邻、或处于同一 `FROM` 片段中的逗号连接一起标准化为 `INNER JOIN`，并在差异说明中写明这是“结果集不变的显式内连接改写”。

### 4. Place filters carefully

重点检查 `WHERE` 中剩余谓词：

- 若谓词引用外连接保留侧（未加 `(+)` 的主表），通常继续留在 `WHERE`。
- 若谓词引用被外连接表，而且原本带 `(+)` 或本质上属于连接条件，通常应移入 `ON`。
- 若谓词引用逗号连接中的某张表，但本质是该表与另一表的连接条件，可以在安全时移入对应 `INNER JOIN ... ON`。
- 若谓词引用被外连接表但未带 `(+)`，它可能会把外连接“压回”成内连接；这是高风险场景，必须标记并与用户确认。
- 若存在 `IS NULL`、`NVL`、`COALESCE`、`CASE`、不等值比较、`OR`、函数包裹列、子查询相关条件，先读取 `references/risk-checklist.md` 再判断。

### 5. Preserve untouched SQL

改写时遵守以下最小变更策略：

- 保留原有 `SELECT` 列表顺序与表达式文本。
- 保留未受影响的 `WHERE` 条件顺序。
- 保留注释、hint、CTE、子查询结构、排序、分组、分页写法。
- 若必须新增换行或缩进，只在改写片段附近做最小范围调整。

## Output template

按下面结构返回：

### 改写后的 SQL

```sql
-- 仅改写与 join 标准化有关的部分，其余保持原样
```

### 仅涉及改写的差异说明

- 将 `... = ... (+)` 改为 `LEFT JOIN/RIGHT JOIN`。
- 将可证明不改变结果集的逗号连接改为显式 `INNER JOIN`。
- 将与这些 JOIN 直接绑定的谓词从 `WHERE` 移入 `ON`。
- 其它 SQL 未改动。

### 是否需要业务确认

- **无需确认**：可以明确证明结果集语义保持不变。
- **需要确认**：列出具体风险点，并给出一条简短确认问题，例如：
  - “`b.status = 'Y'` 是否本来就希望把未匹配的 `b` 记录过滤掉？如果是，改写后需要保留为内连接语义。”
  - “`a.id = b.id` 这个逗号连接条件是否就是你希望显式表达的内连接关系？如果还有依赖旧写法过滤顺序的语义，请先确认。”

## High-risk scenarios

遇到以下任一情况，先提示风险，再给“候选改写 + 待确认点”，不要直接当成最终无风险结果：

- `WHERE` 中还有对外连接表的未标记过滤条件。
- `(+)` 或逗号连接相关谓词出现在 `OR`、`IN`、`NOT IN`、`EXISTS`、复杂布尔组合中。
- 同一张表同时参与多个外连接链，且 join graph 不直观。
- 连接谓词里包含函数、表达式、非等值比较。
- 需要在 `LEFT JOIN` 与 `RIGHT JOIN` 之间交换表顺序才能保持“其它 SQL 不变”目标。
- 要把逗号连接改成 `INNER JOIN` 时，需要大范围重排 `FROM` 才能表达清楚。
- 原 SQL 同时混用旧式外连接、ANSI JOIN、逗号连接，且作用域容易混淆。

## Reference loading

- 需要判断“是否可能改变结果集”时，读取 `references/risk-checklist.md`。
- 需要判断某个逗号连接能否安全改成 `INNER JOIN` 时，也读取 `references/risk-checklist.md`。
- 需要给用户解释为什么某个过滤条件必须留在 `WHERE` 或移入 `ON` 时，优先引用其中的场景分类来组织说明。

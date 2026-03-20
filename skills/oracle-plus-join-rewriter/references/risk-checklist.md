# Oracle `(+)` Rewrite Risk Checklist

仅在需要判断“改写是否可能改变结果集”时加载本文件。

## 1. Safe-by-default patterns

通常可直接改写，且结果集应保持不变：

1. 单个简单等值谓词：`a.id = b.id(+)`
2. 同一外表的多列等值匹配，且每个相关谓词都带 `(+)`
3. `WHERE` 中其余条件只引用保留侧主表
4. 逗号连接中的简单等值 join：`from a, b where a.id = b.id`，且没有 `(+)`、`OR`、函数包裹列、非等值比较或额外依赖过滤时机的条件

这类场景通常可以直接输出最终 ANSI JOIN 版本，并说明“仅把旧式外连接或显然的逗号内连接语法改成标准写法”。

## 2. Safe comma-join to INNER JOIN conversion

以下场景通常可以安全地把逗号连接改为 `INNER JOIN`：

```sql
select *
from a, b
where a.id = b.id
  and a.flag = 'Y';
```

可改为：

```sql
select *
from a
inner join b on a.id = b.id
where a.flag = 'Y';
```

### Preconditions

- 连接条件本身是表与表之间的普通连接关系。
- 其余 `WHERE` 条件不会因为把连接谓词移入 `ON` 而改变语义。
- 改写只涉及 join 表达方式，不改变筛选意图。

## 3. Filters on the nullable side

这是最常见风险点。

### Example

```sql
select *
from a, b
where a.id = b.id(+)
  and b.status = 'Y';
```

旧写法虽然包含 `(+)`，但 `b.status = 'Y'` 会过滤掉 `b` 为 `NULL` 的外连接补行，结果更接近“只保留匹配且状态为 Y 的行”。

### How to handle

- 不要默认把 `b.status = 'Y'` 放进 `ON` 或继续留在 `WHERE` 而不解释。
- 明确告诉用户这里存在两种业务意图：
  1. 想保留 `a` 的全部记录，则应移入 `ON`
  2. 想只保留满足 `b.status = 'Y'` 的匹配记录，则结果更接近内连接筛选
- 向用户确认真实意图后再给最终版本。

## 4. OR / mixed boolean logic

`(+)` 或逗号连接条件一旦进入 `OR`、复合布尔表达式、条件分支，ANSI 改写容易改变过滤时机。

### Handling rule

- 明确标记为高风险。
- 先给结构化风险说明，不要声称“结果一定不变”。
- 如需提供候选改写，必须标注“待业务确认”。

## 5. Function-wrapped columns or non-equality predicates

例如：

- `trunc(a.dt) = b.dt(+)`
- `a.amount > b.min_amount(+)`
- `trunc(a.dt) = trunc(b.dt)`
- `a.amount > b.min_amount`

这类写法不仅涉及连接方向，还涉及表达式求值与空值行为。应视为中高风险，至少提示用户验证样例数据。

## 6. Mixed legacy and ANSI joins

若 SQL 已部分使用 `JOIN ... ON ...`，又同时出现逗号连接和 `(+)`：

- 先分清每个表的作用域。
- 只改必要片段。
- 如果必须整体重排 `FROM` 才能表达清楚，应提前说明“无法只做局部文本变更”。

## 7. Confirmation question templates

当需要确认时，可优先使用以下一句话模板：

- “这里对外连接表 `b` 的过滤条件会影响未匹配行是否保留；你希望保留 `a` 的全部记录吗？”
- “这个 `(+)` 处于复合条件中，ANSI 改写可能改变过滤时机；是否以结果集完全一致为最高优先级来处理？”
- “若保持其它 SQL 文本不动，只能生成 `RIGHT JOIN`；你是否接受这种标准写法，还是更希望通过调整表顺序改成 `LEFT JOIN`？”
- “这个 `a.id = b.id` 逗号连接看起来可以安全改成显式 `INNER JOIN`；你是否希望我一并标准化这部分写法？”

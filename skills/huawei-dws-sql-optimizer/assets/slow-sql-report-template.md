## DWS 慢 SQL 分析结论

### 1. 一句话结论
- {{one_line_conclusion}}

### 2. 关键信息
- SQL 类型：{{sql_type}}
- 执行计划类型：{{plan_type}}
- 总耗时：{{total_time}}
- 最重节点：{{heaviest_node}}
- 是否存在分布式传输：{{has_streaming}}
- 是否怀疑数据倾斜：{{skew_level}}

### 3. 慢 SQL 根因
1. {{root_cause_title}}
   - 证据：{{evidence}}
   - 影响：{{impact}}
   - 判断性质：{{certainty}}

### 4. 优化建议（按优先级排序）
1. [{{priority}}] {{action_title}}
   - 原因：{{action_reason}}
   - SQL：

```sql
{{action_sql}}
```

   - 预期收益：{{expected_benefit}}
   - 风险/代价：{{risk_tradeoff}}
   - 验证方式：{{verification_step}}

### 5. 立即可执行的下一步
- {{next_step}}

### 6. 建议补充的信息
- {{missing_info}}

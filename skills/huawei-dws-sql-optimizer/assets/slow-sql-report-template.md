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

### 2.1 证据来源摘要
- MCP 已验证证据：{{mcp_verified_evidence}}
- 用户提供证据：{{user_provided_evidence}}
- 缺失证据：{{missing_evidence}}
- 结论可信度：{{certainty_overview}}

### 3. 慢 SQL 根因
1. {{root_cause_title}}
   - 证据：{{evidence}}
   - 影响：{{impact}}
   - 判断性质：{{certainty}}

### 4. 优化建议（按优先级排序）
1. [高] {{action_title_high}}
   - 原因：{{action_reason_high}}
   - SQL：

```sql
{{action_sql_high}}
```

   - 预期收益：{{expected_benefit_high}}
   - 风险/代价：{{risk_tradeoff_high}}
   - 验证方式：{{verification_step_high}}

2. [中] {{action_title_mid}}
   - 原因：{{action_reason_mid}}
   - SQL：

```sql
{{action_sql_mid}}
```

   - 预期收益：{{expected_benefit_mid}}
   - 风险/代价：{{risk_tradeoff_mid}}
   - 验证方式：{{verification_step_mid}}

3. [低] {{action_title_low}}
   - 原因：{{action_reason_low}}
   - SQL：

```sql
{{action_sql_low}}
```

   - 预期收益：{{expected_benefit_low}}
   - 风险/代价：{{risk_tradeoff_low}}
   - 验证方式：{{verification_step_low}}

### 4.1 案例映射（可选）
- 案例名：{{case_name}}
- 相似证据：{{case_similarity}}
- 关键差异：{{case_difference}}
- 采用原因：{{case_reason}}
- 验证动作：{{case_validation}}

### 4.2 待业务确认项（如有）
- {{business_confirmation_items}}

### 5. 立即可执行的下一步（30 分钟内）
- {{next_step_1}}
- {{next_step_2}}
- {{next_step_3}}

### 6. 基线与变更记录
- 原始基线：{{baseline_metrics}}
- 本次变更类型：{{change_type}}
- 复测方式：{{retest_method}}

### 7. 回归验证清单
- [ ] 最重节点耗时下降
- [ ] `REDISTRIBUTE/BROADCAST/GATHER` 开销下降
- [ ] 扫描输入行数下降
- [ ] 总耗时下降
- [ ] 结果集语义一致（若有 rewrite）

### 8. 回滚预案
- 回滚动作：{{rollback_action}}
- 回滚触发条件：{{rollback_trigger}}

### 9. 建议补充的信息（若证据不足）
- {{missing_info_1}}
- {{missing_info_2}}
- {{missing_info_3}}

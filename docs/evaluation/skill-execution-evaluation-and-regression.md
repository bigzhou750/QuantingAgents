# Skill 执行评测与配对回归

## 背景

Skill 不能只看“有没有被加载”或“最终答案像不像”。系统需要回答四类问题：

1. 该触发时是否触发，不该触发时是否保持安静。
2. 触发后是否真正完成确定性执行步骤。
3. 放入真实 Skill 集合后是否抢任务或拖累其他 Skill。
4. 新版本相对旧版本在同一回归集上是否回退。

本文描述 `add-skill-execution-evaluation-and-regression` 提供的配置、运行变体、评分器、配对回归和自进化发布门禁。

## Skill 评测 Case 配置

Skill 评测通过 `EvalCase.skill_eval` 或 `scoring_criteria.skill_eval` 声明：

```json
{
  "skill_name": "tushare",
  "variant": "full_skill_set",
  "skill_versions": {
    "baseline": "1.0.0",
    "candidate": "1.1.0"
  },
  "route_expectation": {
    "should_trigger": ["tushare"],
    "should_not_trigger": ["eastmoney"],
    "boundary": ["yfinance"]
  },
  "execution_asserts": {
    "required_tools": ["get_market_data"],
    "forbidden_tools": ["bash"],
    "schema_checks": [
      {"field": "open", "required": true}
    ]
  },
  "coexistence": {
    "neighbor_skills": ["eastmoney", "yfinance"],
    "conflict_scenario": "数据源 Skill 不应互相抢任务"
  },
  "critical": true
}
```

旧 case 不带 `skill_eval` 时保持可读，相关评分器返回 `not_configured`，不伪造分数。

## 运行变体

运行配置通过 `config.skill_eval.variant` 控制：

| variant | 行为 | 用途 |
| --- | --- | --- |
| `no_target_skill` | 只排除目标 Skill，其他 Skill、工具和系统 prompt 不变 | 增量价值基线 |
| `skill_only` | 只暴露目标 Skill | 独立执行测试 |
| `full_skill_set` | 使用真实 Skill 集合 | 共存冲突测试 |

默认建议先跑 `no_target_skill` 基线，再跑目标 Skill 或完整集合，避免“全量禁用 Skill”改变太多变量。

## Runtime 事件

评测过程中会落盘两类标准化 trace：

- `skill_route`：记录候选 Skill、最终选中、未选原因和 `route_selected`。
- `skill_execute`：记录 Skill 正文是否加载、读取位置和 `skill_effective`。

`route_selected` 表示 `load_skill` 被选中；`skill_effective` 表示 Skill 正文加载后对后续执行有影响。两者分开记录，避免把“加载了但没用”当成触发成功。

## 评分器

新增三个 Skill 专用 scorer：

- `skill_route`：命中、漏触发、误触发、静默绕过。
- `skill_execution`：必需/禁止工具、必需文件、schema、公式、状态变更和步骤预算。
- `skill_coexistence`：目标 Skill 与相邻 Skill 的成功率差、抢触发和禁止共享覆盖。

确定性断言优先使用程序规则；只有表达质量等开放维度才交给 LLM judge。

## 配对回归与发布门禁

`SkillRegressionGroup` 把 baseline run 和 candidate run 配成一组，要求两个 run 使用同一 dataset 和 dataset version，并保存：

- 目标 Skill 的基线/候选版本。
- 逐 case 的评分 delta、延迟、成本和失败样本。
- critical case 和 gate 结果。

门禁规则：

- critical case 回退 → block。
- `skill_execution` / `safety` 显著回退 → block。
- 平均分提升不能覆盖关键场景回退。
- 管理员在允许覆盖时，可显式覆盖并留下审计记录。

## 自进化集成

自进化验证 Skill 候选时，`verification_service` 会创建配对回归组，并把逐 case 回退写入 `new_regressions`。`promote_service` 在 Skill promote 前检查回归 gate：

- 默认要求 Skill 回归 gate 通过。
- gate 缺失或失败时默认拒绝发布。
- 只有 `EVOLUTION_SKILL_REGRESSION_OVERRIDE_ALLOWED=true` 且调用 promote 时显式传 `allow_skill_regression_override=true`，才允许管理员覆盖。

覆盖结果写入 `EvolutionReceipt.skill_regression_override`。

## 配置

```text
EVOLUTION_SKILL_REGRESSION_REQUIRED=true
EVOLUTION_SKILL_REGRESSION_OVERRIDE_ALLOWED=false
```

## 首期 Golden Set

内置 `skill_golden_cases.json` 覆盖：

- `tushare` 正样本、负样本、边界样本。
- `eastmoney` 资金流正样本。
- `okx-market` 订单簿正样本。
- `yfinance` 美股行情正样本。
- `ccxt` 跨所比价和共存场景。
- critical 回归样本，断言 OHLCV 字段完整。

可通过评测后台的 Golden Set 导入入口导入；`dataset_service.import_golden_cases` 会同时导入普通 Golden Set 和 Skill Golden Set。

## 兼容性

- 新字段全部可选。
- 旧 trial 无 Skill trace 时返回 `legacy_unverified`。
- 旧 run 无配对回归组时不进入 critical 门禁。
- 未启用 Skill 评测的 scorer 返回 `not_configured`，不影响既有评分语义。

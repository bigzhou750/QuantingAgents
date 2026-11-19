# 线上 Bad Case 自动发现与评测样本回流设计

## 1. 背景

当前项目已经具备评测平台、Bad Case 池、自进化提案、候选验证、发布和回滚等基础能力，但线上链路仍主要依赖管理员手动提交样本。

本设计记录两个核心问题：

1. 什么样的线上会话应该被识别为 Bad Case。
2. Bad Case 如何可靠地回流为评测样本，避免把坏输出、错误标签或不可复现上下文带入评测集。

目标不是把所有低分样本都塞进 Bad Case 池，而是建立一套带证据、带置信度、可去重、可复现、可追踪的样本治理流程。

## 2. 目标闭环

```text
线上会话与 trace
    |
    v
候选信号采集
    |
    v
质量判定与置信度计算
    |
    +--> 直接入 Bad Case 池
    +--> 进入人工复核队列
    +--> 丢弃或仅记录指标
    |
    v
样本去重与上下文快照
    |
    v
按类型回流为评测 Case
    |
    v
评测集版本化
    |
    v
针对 Bad Case 的回归验证
    |
    v
触发提案、候选验证、门禁、发布
    |
    v
发布后线上观测
    |
    +--> 新 Bad Case
    +--> Stop
    +--> Rollback
```

## 3. Bad Case 的定义

Bad Case 应被定义为“线上 Agent 的行为或输出违反了一个可验证的质量、安全、任务或运行约束”，而不是简单的低分结果。

### 3.1 执行失败

这是最确定的一类，可直接自动入池：

- `attempt.failed`
- Agent runtime 返回失败状态
- 超时
- 任务被异常中断
- 输出为空
- 缺少 `final_report` 或终态结果

建议默认置信度为 `1.0`，失败原因来自 runtime 或任务状态。

### 3.2 工具与轨迹失败

包括：

- 工具调用返回错误
- 工具参数非法
- 权限拒绝
- 连续重复调用同一个工具
- 疑似死循环或 stall
- 工具失败率超过阈值
- 完成任务时遗漏必要工具或证据步骤

可复用 `trajectory` scorer、工具事件和 `mcp.warning` 等 trace 信号。

明确的权限违规、安全工具误调用和死循环可以直接入池；普通轨迹低分建议先进入复核队列。

### 3.3 安全与合规风险

包括：

- 敏感信息泄露
- API key、token、密码或个人信息泄露
- 未授权访问工具或数据
- 危险工具调用
- 投资建议越界
- 使用不可信内容作确定性投资结论

安全风险应自动创建 Bad Case，保存风险标签和证据引用，但进入正式 Golden Set 前必须人工复核。

### 3.4 证据、事实与幻觉问题

包括：

- 输出 claim 没有证据支撑
- claim 与证据矛盾
- 证据来源为空或不可信
- 数据时间不匹配
- 虚构行情、财务数据或新闻内容
- 结论确定性过强，但证据不足

可复用 `evidence_quality` scorer 的 claim、evidence、unsupported ratio、contradiction ratio 和幻觉预测标签。

单一启发式信号不应直接判定为严重幻觉。建议至少满足以下条件之一：

- 存在明确矛盾证据。
- 多个独立规则同时命中。
- 规则信号与 LLM Judge 结果一致，且两者置信度都达到阈值。

### 3.5 输出质量问题

包括：

- 缺少用户要求的内容
- 输出格式不完整
- 缺少风险披露
- 分析过于笼统
- 结论没有回答用户问题
- 逻辑推理质量不足

这类问题主观性较强，不建议仅凭一次 LLM Judge 低分直接自动入池。默认进入人工复核队列，只有在重复出现或有用户反馈佐证时才升级为自动 Bad Case。

### 3.6 用户反馈

包括：

- 用户显式点击“回答错误”或“没有帮助”
- 用户提交文字反馈
- 用户要求重新回答并指出具体错误
- 用户举报风险或事实错误

用户反馈是高价值信号，但仍需保存原始反馈文本、关联会话和输出版本。明确负反馈可以直接创建 Bad Case；反馈内容模糊时进入复核队列。

### 3.7 运行质量问题

包括：

- 延迟异常
- token 或成本异常
- 工具调用次数异常
- 资源消耗超出预算

这类样本应作为“运行质量 Bad Case”独立分类，不与内容质量 Bad Case 混合，避免自进化错误地修改 Prompt 或 Skill 来解决基础设施问题。

## 4. 自动发现架构

建议将发现流程拆成四层：

```text
Layer 1: Event Capture
  收集 session、task、message、runtime event、trace、final output

Layer 2: Signal Extraction
  将原始事件转成结构化信号

Layer 3: Adjudication
  合并多个信号，计算置信度、风险等级和失败家族

Layer 4: Routing
  直接入池、人工复核、仅记录指标或丢弃
```

### 4.1 现有接入点

`app/services/vibe_agent/service.py` 中的 `ingest_worker_event()` 已经处理以下线上事件：

- `attempt.started`
- `attempt.completed`
- `attempt.failed`
- `attempt.cancelled`
- `tool_call`
- `tool_result`
- `evidence`
- `mcp.warning`

该函数是自动发现执行失败、工具失败和安全信号的主要接入点。完成任务后，还需要基于最终输出触发输出质量、证据质量和 LLM Judge 检查。

### 4.2 统一信号结构

建议每个候选信号至少包含：

```json
{
  "signal_type": "evidence.unsupported_claim",
  "failure_family": "evidence_hallucination",
  "score": 0.82,
  "confidence": 0.85,
  "severity": "medium",
  "reason": "Claim 未找到证据支撑",
  "evidence_refs": ["event_123"],
  "detector_name": "evidence_quality",
  "detector_version": "2.1.0"
}
```

Bad Case 不应只保存一个最终分数，而应保存形成结论的信号列表，便于复核、重算和后续分析。

### 4.3 推荐路由策略

| 条件 | 路由 | 说明 |
|---|---|---|
| runtime 明确失败、超时、空输出 | 直接入池 | 事实明确，置信度高 |
| 明确安全风险或权限违规 | 自动入池 + 强制复核 | 可以先阻断和统计，但不能直接进入 Golden Set |
| 明确用户负反馈 | 直接入池 | 保留反馈原文 |
| 多个规则信号一致 | 自动入池 | 例如 unsupported claim + 无 evidence |
| 单一 LLM Judge 低分 | 复核队列 | 防止 Judge 误判污染数据 |
| 偶发低分且无严重风险 | 仅记录指标 | 等待重复性或更多证据 |
| 延迟、成本异常 | 运行质量池 | 不作为内容修复样本 |

对于软质量问题，建议引入重复性条件，例如同一失败模式在 `N` 次窗口中出现至少 `K` 次，或者同一输入的多次运行中有超过一定比例失败。

## 5. Bad Case 数据结构建议

现有 `EvalBadCase` 已有来源、输入、输出、失败原因、风险级别、trace、发布回执和 artifact 版本字段。为了支持自动治理，建议增加以下逻辑字段：

```json
{
  "bad_case_id": "bc_xxx",
  "source": "online_sampling",
  "failure_family": "evidence_hallucination",
  "failure_reason": "输出包含与证据矛盾的结论",
  "risk_level": "high",
  "detection_status": "auto_confirmed",
  "detection_confidence": 0.91,
  "detection_signals": [],
  "review_required": true,
  "review_status": "pending",
  "dedup_key": "sha256:...",
  "source_context": {
    "user_id_hash": "...",
    "session_id": "...",
    "task_id": "...",
    "trace_id": "...",
    "created_at": "...",
    "data_window": {},
    "artifact_versions": {},
    "release_receipt_id": "..."
  },
  "reflow_status": "pending",
  "reflow_case_id": null,
  "label_version": "1.0.0"
}
```

原始输入、输出和 trace 应执行脱敏、大小限制和访问控制。Bad Case 的内容可能包含用户问题、账户信息或内部数据，不能直接照搬到外部观测平台或共享评测集。

## 6. 可靠回流规则

### 6.1 执行失败回流

执行失败应转成“流程回归 Case”，而不是普通问答 Case：

```json
{
  "input": {
    "prompt": "原始用户问题"
  },
  "expected_output": null,
  "scoring_criteria": {
    "must_complete": true,
    "must_not_timeout": true,
    "must_have_final_report": true,
    "must_not_repeat_failure": "timeout"
  }
}
```

### 6.2 工具和轨迹问题回流

应将失败模式写进评分标准：

```json
{
  "input": {
    "prompt": "原始用户问题"
  },
  "expected_output": null,
  "scoring_criteria": {
    "max_repeated_tool_calls": 2,
    "max_tool_failure_rate": 0.2,
    "required_tools": [],
    "must_not_have_permission_violation": true
  }
}
```

### 6.3 证据和幻觉问题回流

证据或幻觉 Bad Case 应使用 claim 级标签，而不是把线上坏输出当作期望答案：

```json
{
  "input": {
    "prompt": "原始用户问题"
  },
  "expected_output": null,
  "scoring_criteria": {
    "min_evidence_coverage": 0.8,
    "max_unsupported_ratio": 0.1,
    "max_contradiction_ratio": 0.0,
    "must_include_data_time_range": true
  },
  "metadata": {
    "source_bad_case_id": "bc_xxx",
    "observed_failure_family": "evidence_hallucination",
    "truth_labels": []
  }
}
```

### 6.4 安全问题回流

安全样本应保存：

- 风险类型
- 命中的规则
- 相关 trace event
- 原始输出片段
- 人工确认结果
- 标签版本

只有人工确认后的安全样本，才适合进入长期 Golden Set。未确认样本可以进入安全回归池，但必须标记为待复核。

### 6.5 用户反馈回流

用户反馈可以直接形成回归候选，但要区分：

- 用户说“答案错了”：需要后续事实核验或人工标注。
- 用户说“答案没用”：更适合转成输出质量或任务完成度问题。
- 用户指出具体错误：可以直接作为失败原因和标注依据。

如果没有正确参考答案，不能自动生成普通 `expected_output`。应先保留为负向回归样本，或由人工补充正确答案。

## 7. 数据集分层

建议至少拆分四类数据集：

### 7.1 Online Regression Set

允许高置信度执行失败、工具失败和重复性质量失败自动进入。用途是快速发现修复是否解决了真实线上问题。

### 7.2 Review Queue

存放 LLM Judge 低分、单一证据启发式命中、模糊用户反馈和安全待确认样本。人工复核后再决定进入其他数据集。

### 7.3 Detector Evaluation Set

用于验证幻觉、证据和安全检测器本身。需要人工真值、标签版本、预测标签和混淆矩阵，不能与 Agent 行为回归集混用。

### 7.4 Golden Set

只存放已经人工确认、期望行为明确、上下文可复现的高价值样本。不能因为 badcase 数量达到阈值就直接写入 Golden Set。

## 8. 去重与版本化

### 8.1 去重指纹

建议根据以下字段生成 `dedup_key`：

```text
normalized_input
+ failure_family
+ normalized_failure_signature
+ artifact_version
+ data_window
```

重复出现时，不重复创建 Case，而是更新：

- `occurrence_count`
- `first_seen_at`
- `last_seen_at`
- 受影响版本列表
- 不同用户或会话数量

### 8.2 数据集版本

每次回流都应产生新的数据集 patch version。评测运行必须固化：

- dataset version
- case 内容快照
- scorer 配置和版本
- judge 配置和 rubric 版本
- 数据时间窗口
- artifact 版本

线上金融数据如果无法恢复历史快照，则只能验证结构、流程和风险约束，不能把当前数据下的事实结果当作历史真值。

## 9. 回流前置校验

一个 Bad Case 进入评测集前，应至少通过以下检查：

1. 输入、输出和失败原因不为空。
2. 失败家族属于已注册枚举。
3. 至少存在一个检测信号或人工标注。
4. trace 引用可查询，或明确标记为不可回放。
5. artifact 版本和时间窗口存在时，格式合法。
6. 未命中重复指纹，或明确执行合并。
7. 不把原始坏输出直接写入 `expected_output`。
8. 安全、事实和幻觉样本具有正确的复核状态。
9. 脱敏检查通过。
10. 回流目标数据集符合该类型样本的准入策略。

## 10. 与自进化闭环的关系

Bad Case 自动创建后，不应直接修改生产 artifact。推荐链路为：

```text
Bad Case created
    → dedup / aggregate
    → threshold or severe signal trigger
    → create evolution proposal
    → identify failure surface
    → generate candidate
    → run original Bad Case + regression set
    → run fixed validation set
    → quality / safety / cost / latency gate
    → human approval or policy-based auto approval
    → promote
    → post-release observation
```

当前项目的自进化 proposal 生成仍然偏规则启发式，例如 Skill 目标多数会落到通用 artifact，候选 diff 也需要逐步从通用描述升级为基于 trace 和失败模式的具体修改。

## 11. MVP 建议

第一阶段不需要一开始就让 LLM Judge 决定所有 Bad Case，建议按以下顺序落地：

1. 自动收集 runtime 明确失败、超时、空输出和工具错误。
2. 增加用户负反馈接口，并保留反馈原文。
3. 增加采样、去重、脱敏和 `detection_signals` 字段。
4. 将硬失败自动回流到 `Online Regression Set`。
5. 将安全、证据、幻觉和 LLM Judge 样本先送入 `Review Queue`。
6. 修正回流语义，禁止把坏输出作为 `expected_output`。
7. 让候选验证强制包含触发本次提案的 Bad Case。
8. 再逐步根据人工复核结果校准软质量信号的自动入池阈值。

## 12. 关键指标

建议监控以下指标来判断自动闭环是否健康：

- Bad Case 自动判定量
- 自动判定后的人工确认率
- 各检测器的 Precision、Recall、F1
- 重复 Bad Case 合并率
- Bad Case 到 Eval Case 的回流成功率
- 回流样本的不可回放率
- 线上 Bad Case 被候选修复覆盖的比例
- 候选验证通过率
- 发布后回归复现率
- 发布后新增 Bad Case 率
- 自动回滚触发率
- 误回滚率

其中最重要的是人工确认率和发布后回归复现率：前者衡量自动发现是否产生噪音，后者衡量回流样本是否真的能代表线上问题。

## 13. 待决策问题

以下问题需要在进入实现前明确：

1. “完整自动化”是否允许生产发布保留人工审批？
2. 线上质量评分是否允许调用 LLM Judge，还是只使用规则和 trace 信号？
3. 哪些安全事件可以自动阻断，哪些只进入复核队列？
4. 金融数据无法完整快照时，哪些类型的 Case 允许回流？
5. Online Regression Set 是否与现有 Golden Set 分离保存？
6. 发布后观测触发 rollback 时，是自动执行还是先创建 rollback candidate？

当前建议的默认答案是：硬失败自动入池，软质量先复核，安全样本强制人工确认，生产发布保留人工门禁，线上回归集与 Golden Set 分离。

## 14. 当前实现映射

本方案的第一版实现已经接入以下路径：

- `app/services/vibe_agent/service.py` 的终态事件异步调用线上采集器。
- `app/services/eval/online_badcase_service.py` 负责 pseudo-trial、硬失败信号、可选 scorer 信号和路由判定。
- `app/services/eval/bad_case_service.py` 负责去重、脱敏、候选/确认状态、复核和策略化回流。
- `/api/vibe-agent/sessions/{session_id}/tasks/{task_id}/feedback` 接收用户反馈。
- `/api/eval/bad-cases/review-queue` 和 `/api/eval/bad-cases/{bad_case_id}/review` 提供管理员复核。
- `/api/eval/bad-cases/{bad_case_id}/convert` 保持兼容，但不再复制坏输出为期望输出。

自动采集仍由 `ONLINE_BADCASE_ENABLED` 控制，LLM Judge 软信号由 `ONLINE_BADCASE_ENABLE_JUDGE` 单独控制。

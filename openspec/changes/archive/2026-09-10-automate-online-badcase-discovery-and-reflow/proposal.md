## Why

当前 Bad Case 池主要依靠管理员手动通过后台或 API 入池，真实线上的执行失败、工具错误、安全风险和用户反馈不会自动变成可评测样本。自进化闭环缺少“线上问题自动发现 → 可靠回流评测集”这一段，导致大量线上问题无法自动进入回归验证和候选修复链路。

现在项目已经具备 Vibe Agent 事件、trace、评分器、Bad Case 池和评测集版本能力，补上自动发现与可靠回流比推倒重做更合适，也是让自进化闭环真正面向线上数据的必要一步。

## What Changes

- 在 Vibe Agent 线上事件接入点增加自动识别：runtime 失败、超时、空输出、工具错误、死循环、权限违规、安全风险、mcp warning 和显式用户反馈。
- 为线上样本增加结构化判定层：`failure_family`、`detection_signals`、`detection_confidence`、`review_required`、`dedup_key` 和上下文引用。
- 新增自动路由策略：高置信硬失败直接入池，LLM Judge、证据低分和模糊反馈进入复核队列，偶发低分仅记录指标。
- 新增去重与样本治理：相同输入、失败家族、artifact 版本和时间窗口的样本合并，不重复创建 Bad Case 和评测 Case。
- 修正回流语义：禁止把线上坏输出直接作为 `expected_output`；根据失败家族转成回归 Case、负向 Case 或带标签样本。
- 新增评测集分层：Online Regression、Review Queue、Detector Evaluation 和 Golden Set，保持系统已有评测集/API 兼容。
- 新增 Bad Case 到自进化触发器的链路：达到阈值或出现高风险事件时，可按现有 trigger 机制创建候选提案，不直接修改生产 artifact。
- 在研究工作台增加用户反馈入口，用于标记回答错误、内容无用或具体错误。
- 保持现有 Bad Case 手工 API 和页面可用，新增字段均可选，不破坏旧数据反序列化和旧流程。

**非目标**
- 不在本 change 中实现自动审批、自动发版或自动回滚。
- 不重做 Vibe Agent runtime 执行链路。
- 不引入新的外部评测框架或观测平台。

## Capabilities

### New Capabilities
- `online-badcase-automation-and-reflow`: 线上问题样本的自动发现、质量判定、去重、复核路由、回流评测样本和触发自进化提案。

### Modified Capabilities
- 无。本 change 在现有 `agent-evaluation-platform` 之上新增线上样本治理能力，不改变已有稳定契约。

## Impact

- `app/services/vibe_agent/service.py`：在事件接入点增加采样、判定和入池 hook。
- `app/services/eval/bad_case_service.py`：扩展 Bad Case 自动创建、去重、复核状态和按语义回流。
- `app/models/eval.py`：扩展 Bad Case、检测信号和回流上下文模型。
- `app/services/eval/dataset_service.py`：支持 Online Regression 等分层数据集和带来源的回流。
- `app/services/eval/scorer_hub.py`：复用或扩展评分器，用于线上会话质量判定。
- `app/services/evolution/trigger_service.py`：支持 Bad Case 事件触发的阈值检查和高风险升级。
- `frontend/`：研究工作台增加用户反馈入口，Bad Case 页面展示检测信号和复核状态。
- 数据存储：新增或扩展 MongoDB 集合字段与索引，不改动已有核心字段。
- 文档与测试：补充设计、API、数据结构、边界条件和回归测试。

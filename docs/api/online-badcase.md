# Online Bad Case API

线上 Bad Case 自动发现默认关闭，需配置 `ONLINE_BADCASE_ENABLED=true`。自动评分在后台异步执行，不阻塞 Vibe Agent 的 SSE、任务状态和最终输出。

## 用户反馈

```http
POST /api/vibe-agent/sessions/{session_id}/tasks/{task_id}/feedback
```

请求体：

```json
{
  "feedback_type": "wrong_answer",
  "content": "可选的具体反馈"
}
```

请求必须由会话所属用户发起，并且 `session_id` 和 `task_id` 必须属于同一用户。

## Bad Case 查询与复核

```http
GET /api/eval/bad-cases?detection_status=candidate&review_status=pending
GET /api/eval/bad-cases/{bad_case_id}
GET /api/eval/bad-cases/review-queue
POST /api/eval/bad-cases/{bad_case_id}/review
```

复核请求体：

```json
{
  "action": "approve",
  "failure_family": "evidence_hallucination",
  "comment": "已核验为证据不足"
}
```

`action` 只支持 `approve` 和 `reject`，接口沿用评测平台管理员权限。

## 线上自动采集字段

自动生成的 Bad Case 会保存：

- `failure_family`
- `detection_signals`
- `detection_confidence`
- `detection_status`
- `review_status`
- `dedup_key`
- `source_context`
- `artifact_version` 和 `release_receipt_id`

输入、输出和反馈会执行敏感信息脱敏与文本长度限制。

## 回流

```http
POST /api/eval/bad-cases/{bad_case_id}/convert
```

回流接口仍保持原有请求结构，但会按失败家族构建评分标准，不会再把线上坏输出作为 `expected_output`。执行/工具失败默认进入 Online Regression 语义；证据、幻觉和安全样本根据复核状态进入 Detector Evaluation、Review Queue 或 Golden 语义。

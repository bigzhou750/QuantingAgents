# Agent 自进化闭环使用文档

## 概述

自进化闭环在评测平台之上建立了 **Trigger → Proposal → Verify → Promote/Rollback** 的受控经验沉淀机制。它将失败样本、人工复核和评测指标转化为候选 Skill/Prompt/Policy/Rubric/Case 变更，经固定评测集验证和人工审批后再生效。

Skill 候选的验证与发布门禁细节见 [Skill 执行评测与配对回归](evaluation/skill-execution-evaluation-and-regression.md)。

## 配置

在环境变量或配置中设置：

```bash
EVOLUTION_AUTOMATION_MODE=semi-auto       # manual / semi-auto / auto
EVOLUTION_HUMAN_GATE=true                 # 生产环境必须开启
EVOLUTION_TRIGGER_REGRESSION_THRESHOLD=0.05
EVOLUTION_TRIGGER_BAD_CASE_COUNT=10
EVOLUTION_BUDGET_MAX_RUNS_PER_DAY=5
EVOLUTION_DAILY_COST_BUDGET_USD=10
EVOLUTION_CHANGE_BUDGET_CHARS=20000
EVOLUTION_COOLDOWN_MINUTES=60
EVOLUTION_REQUIRE_SMOKE_TEST=true
EVOLUTION_SCHEDULE_CRON=             # 留空表示不注册定时任务
```

## 核心流程

### 1. Trigger（触发）

系统支持四种触发方式：
- **评测完成触发**: eval run 完成后自动检查失败率和聚类
- **趋势回退触发**: 最近 N 次 run 的成功率下降超过阈值
- **Bad Case 阈值触发**: 未处理的 Bad Case 数量超过阈值
- **定时触发**: 通过 cron 表达式配置（默认关闭）

### 2. Proposal（候选提案）

触发后系统自动生成候选提案，包含：
- 目标 artifact（Skill/Prompt/Policy/Rubric/Case）
- 候选 diff 和变更原因
- 关联失败样本
- 风险等级评估
- 回滚策略

**安全边界**: 禁止修改核心代码、测试集、评分口径和样本切分。

### 3. Verify（验证）

候选版本通过 sandbox 临时覆盖机制在固定 dataset version 上回放：
- 基线 run vs 候选 run 对比
- pass@k、pass^k、grounding、judge 等指标
- 新增 regression 检测

### 4. Approve（审批）

管理员在前端工作台审查候选：
- 查看触发来源、失败模式、diff、验证结果
- 批准 / 拒绝 / 评论
- 完整审计轨迹

### 5. Promote / Rollback

- **Promote**: 将已批准的候选写为正式 artifact 新版本
- **Rollback**: 恢复到指定稳定版本
- **Stop**: 紧急停止（预算超限、安全退化等）

Promote 前必须同时满足：proposal 已验证、verification sandbox 已清理、Gate 通过、artifact 基线版本未变化、人工审批有效和 smoke test 通过。版本冲突或任一门禁失败都会拒绝发布。

候选验证的 overlay context 会记录 proposal、artifact、基线版本、候选版本、dataset version 和 sandbox 路径，并通过 `evolution.overlay.loaded` trace 事件记录实际加载的候选文件。正式运行没有 overlay context，只读取 active artifact。

## API 端点

所有端点在 `/api/evolution` 下，需要管理员权限。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| GET/PUT | /config | 获取/更新配置 |
| GET | /artifacts | 列出 artifact |
| POST | /artifacts | 注册 artifact |
| GET | /artifacts/{id} | artifact 详情 |
| GET | /artifacts/{id}/versions | 版本历史 |
| POST | /artifacts/{id}/rollback | 回滚 |
| GET | /proposals | 列出提案 |
| GET | /proposals/{id} | 提案详情 |
| POST | /proposals/{id}/verify | 启动验证 |
| GET | /proposals/{id}/verification | 验证结果 |
| POST | /proposals/{id}/approve | 批准 |
| POST | /proposals/{id}/reject | 拒绝 |
| POST | /proposals/{id}/comment | 评论 |
| GET | /proposals/{id}/audit | 审批记录 |
| POST | /proposals/{id}/promote | 发布 |
| POST | /proposals/{id}/stop | 停止 |
| GET | /receipts | 回执列表 |
| GET | /receipts/{id} | 回执详情 |
| GET | /audit-log | 事件日志 |
| GET | /stats | 统计概览 |

## Artifact Registry

可自进化的资产类型：
- **Skill**: SKILL.md 文件，存储在 `~/.zhitouagent/skills/user/` 覆盖层
- **Prompt**: 系统提示词模板，存储在 MongoDB
- **Policy**: routing/grounding/safety 策略，存储在 MongoDB
- **Rubric**: LLM Judge 评分标准，存储在 MongoDB
- **Case**: 评测用例，复用现有 eval_cases 集合

每个 artifact 都有版本号（semver）、内容哈希和完整的版本历史。

## 前端页面

- **候选提案** (`/evolution/proposals`): 列表 + 筛选 + 状态统计
- **提案详情** (`/evolution/proposals/:id`): 完整生命周期视图
- **Artifact 管理** (`/evolution/artifacts`): 注册表 + 版本历史 + 回滚
- **进化回执** (`/evolution/receipts`): promote/rollback/stop 记录

## 安全机制

1. **Allowlist**: 只允许修改已注册的 artifact
2. **Forbidden targets**: 核心代码、测试集、评分口径不可修改
3. **Human gate**: 生产环境默认要求人工审批
4. **Sample isolation**: 候选流程不访问测试集
5. **Stop hook**: 预算超限、重复失败、安全退化时自动停止
6. **Audit trail**: 所有操作有完整审计记录
7. **Version rollback**: 任何版本都可回滚

8. **Scope isolation**: candidate 只能使用 validation split 和固定 dataset version，不能访问 test/holdout/production split
9. **Idempotency**: proposal 指纹、定时窗口锁和 promote 锁防止重复提案及并发发布
10. **Notification outbox**: 通知失败会记录 delivery 状态，不会伪造“已通知”

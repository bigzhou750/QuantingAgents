## Context

自进化依赖现有评测平台作为 verify 层，但不应让 agent 直接修改生产代码或绕过人工审批。两篇调研笔记的共同原则是：先定义可改和不可改边界，再通过版本管理、样本隔离、回放验证和门禁控制，让经验以受控 artifact 的形式生效。

## Goals / Non-Goals

**Goals:**
- 建立 trigger -> proposal -> verify -> promote -> rollback 的自进化闭环。
- 把 bad case、人工复核、失败聚类和趋势回退转成候选变更。
- 让候选变更只作用于 Skill、Prompt、routing policy、grounding policy、rubric 和 case。
- 每个候选都可审计、可验证、可回滚。
- 提供前端工作台让管理员审批、验证和发布候选。

**Non-Goals:**
- 不允许 agent 自主修改核心代码。
- 不允许候选流程访问测试集或改变样本切分。
- 不把自进化做成无限循环或自动上线机制。
- 不替代人工复核；高风险变更默认需要人工审批。

## Decisions

### 1. 使用受控 artifact registry

自进化只操作登记过的 artifact：Skill、Prompt、Policy、Rubric、Case。  
每个 artifact 需要有 id、类型、路径或存储位置、当前版本、allowlist、owner 和回滚策略。

### 2. Proposal 是一等对象

候选变更不直接应用，而是先形成 proposal，保存触发来源、失败模式、关联样本、候选 diff、原因、预算、风险和状态。  
这让人能在前端审查，而不是让 agent 隐式修改文件。

### 3. Verify 复用评测平台

候选版本通过现有 eval runner 回放固定 dataset version，并记录 baseline 与 candidate 的指标差异。  
验证指标包括 `pass@k`、`pass^k`、grounding、judge、失败率、延迟、成本和新 regression。

### 4. Promote 与 Rollback 分离

Promote 只负责把通过验证的候选写回正式 artifact 版本。Rollback 只负责恢复稳定版本。  
分离后，失败候选也能保留作为经验，不会污染正式版本。

### 5. 默认 semi-auto，生产需要 human gate

系统可以自动生成候选 diff 和验证 run，但生产默认不能自动 promote。  
只有低风险配置或实验环境可以开启 `auto`。

### 6. 经验分层沉淀

原始经验保存为 trace、review、bad case、score 和 receipt。  
正式经验沉淀为 Skill、Policy、Rubric、Case 和版本说明。agent 执行时只读取已批准的正式资产。

## Risks / Trade-offs

- [Risk] 候选变更过大导致不可解释 -> Mitigation: 每个 proposal 限制 change budget，并要求说明单一主要假设。
- [Risk] 优化过拟合验证集 -> Mitigation: 强制训练/验证/测试隔离，测试集不进入自动优化。
- [Risk] 自动化改坏生产 -> Mitigation: allowlist、human gate、release gate、rollback 和 stop hook。
- [Risk] proposal 数量过多 -> Mitigation: 失败聚类和阈值触发，避免每个失败都生成候选。
- [Risk] artifact 写回冲突 -> Mitigation: 使用版本号和 diff 审批，promote 前检查基线版本。

## Migration Plan

1. 新增自进化数据模型和只读工作台，先展示候选状态。
2. 接入 eval run completed 和 bad case 阈值触发，但默认只生成建议。
3. 加入候选 diff、验证 run 和审批。
4. 最后启用 promote/rollback 写回能力，生产默认要求人工审批。

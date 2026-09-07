# 2026-09-04 自进化与发布链路会话总结

## 1. 这次会话讨论了什么

本次主要围绕自进化闭环、Skill 的加载与发布、生产级 artifact 管理、提案详情页的可读性，以及如何把现有实现升级到更接近生产的控制面展开。

## 2. Skill 目录和加载机制

### 用户层目录是什么

- 路径：`~/.vibe-trading/skills/user/`
- 含义：操作系统用户级别的本地正式生效层，不是业务账号级别
- 作用：运行时会优先扫描这里，用户层同名 skill 会覆盖内置 skill

### 什么时候会被加载

- Agent 启动 / 新会话构建 system prompt 时
- 调用 `load_skill(name=...)` 时
- 本会话里刚写入的 skill，后续可通过磁盘回读进入 `load_skill`

### 这个目录里有什么

- `SKILL.md`
- `references/`
- `templates/`
- `examples/`
- `assets/`

### 结论

- 这个目录一开始可以为空
- 大模型不会凭空“生成可用 skill”，必须通过工具或发布流程写进去
- 写入后会覆盖内置层同名 skill

## 3. 当前项目里的自进化闭环

### 现有流程

1. 评测运行完成
2. `trigger_service` 判断是否触发自进化
3. `clustering.py` 识别失败面
4. `proposal_service` 生成提案并映射目标 artifact
5. `verification_service` 创建 sandbox 并跑候选验证
6. `approval_service` 处理审批
7. `promote_service` 发布正式版本
8. `receipt_service` 留痕回执

### 现在已经有的版本管理

- `artifact_registry` 负责 artifact 注册与版本
- `Proposal` / `VerificationRun` / `EvolutionReceipt` 记录生命周期
- Skill 在 promote 时会写入用户层目录并失效缓存

## 4. 为什么现在还不算生产完整闭环

下面这些点是会话里明确指出的生产缺口：

- baseline 还没有在提案创建时真正锁死
- `EVOLUTION_COOLDOWN_MINUTES` 还只是配置，没真正进入触发去重
- promote / rollback 仍偏补偿式一致性，不是硬原子边界
- post-release 观测还没自动回流成 Bad Case / stop / rollback
- overlay 仍偏 prompt 注入式，隔离边界还可以继续收紧

### 补充判断

- 这些问题不属于“提案详情页 UX”，而属于后端生产闭环控制面
- 所以我把它们拆成了独立 change，而不是塞进页面改版里

## 5. 评测后如何判断该优化哪一类 artifact

当前实现是“失败聚类 + 规则映射”：

- `trigger_service` 收集 run 完成、趋势回退、Bad Case 阈值等触发
- `cluster_failed_trials()` 按错误、scorer、source 聚类
- `identify_primary_failure_surface()` 把失败面映射成：
  - `skill`
  - `prompt`
  - `policy`
  - `rubric`
  - `case`

然后 `proposal_service` 再把 surface 映射成具体目标 artifact_id，例如：

- `art_skill_general`
- `art_prompt_system_default`
- `art_policy_grounding`
- `art_policy_safety`
- `art_rubric_financial_default`
- `art_case_dataset_<dataset_id>`

### 现阶段的局限

- 这是规则启发式，不是强学习归因
- 多数情况下只能定位到类型层级，不能精准到某个具体 skill 文件

## 6. skill 类型的候选是怎么生成的

- `skill` 类型会基于当前正式版本生成候选内容
- 验证时会把当前 `SKILL.md` 读出来
- 再把候选 diff 应用上去，写入 sandbox 中的候选 skill
- 然后用候选 run 和 baseline run 做对比

### 重要结论

- 现在不是“自动新建一个全新 skill 名称”
- 更像是“以当前 skill 为 baseline 生成候选版本，在 sandbox 中验证”
- 现阶段 skill 目标大多还是通用的 `art_skill_general`

## 7. 为什么要拆出三个 OpenSpec change

### 1) `evolution-proposal-detail-page-ux-refresh`

目的：优化自进化提案详情页的交互和展示，让人一眼看懂页面在表达什么。

覆盖内容：

- 提案摘要
- 变更区块
- 验证区块
- 审批 / 发布区块
- JSON 从主视图降级为辅助视图

### 2) `evolution-release-pipeline-hardening`

目的：把发布升级成版本化、可审计、可回滚、可分环境的正式链路。

覆盖内容：

- artifact 版本推进
- 类型化 materialization
- 发布前后校验
- 回滚
- 发布历史与回执可见性

### 3) `evolution-production-closure-hardening`

目的：补齐生产完整闭环里最关键的控制面缺口。

覆盖内容：

- baseline 锁定
- cooldown 去重
- 发布边界收紧
- post-release 自动回流
- overlay 隔离收紧

## 8. 最终结论

- `~/.vibe-trading/skills/user/` 是用户层正式生效目录
- 当前项目已经有自进化闭环雏形，但生产级边界还不够硬
- 评测后定位优化类型，当前靠失败聚类和规则映射
- skill 候选是基于当前版本生成 sandbox 里的候选再比较
- 我已经把这次会话里的关键讨论拆成了 3 个 OpenSpec change，后续可直接进入实现


## Purpose

这个能力用于把自进化 artifact 的发布从“写本地文件即可生效”升级为“版本化、可审计、可回滚、可分环境发布”的正式链路，让生产环境不再依赖开发者机器的临时目录或单次写盘结果。

## ADDED Requirements

### Requirement: Release pipeline must publish immutable versions
系统 SHALL 将每一次发布记录为不可变的 artifact 版本，并 SHALL 为每个环境维护当前生效版本指针。

#### Scenario: Promote a new version
- **WHEN** 某个已批准且已验证通过的 artifact 被发布
- **THEN** 系统 SHALL 创建新的版本记录，并 SHALL 将该环境的当前版本指针切换到该版本

#### Scenario: Historical version remains available
- **WHEN** 新版本成为当前版本
- **THEN** 系统 SHALL 保留之前的版本记录，以便审计和回滚

### Requirement: Release pipeline must support type-specific materialization
系统 SHALL 为不同 artifact 类型提供统一的发布入口，并 SHALL 根据 artifact 类型将版本 materialize 到对应的正式生效位置。

#### Scenario: Skill version is published
- **WHEN** 发布目标是 Skill artifact
- **THEN** 系统 SHALL 将对应版本 materialize 到运行时可读取的 Skill 生效位置，并 SHALL 让运行时能够读取到该版本

#### Scenario: Non-Skill artifact is published
- **WHEN** 发布目标是 Prompt、Policy、Rubric 或 Case
- **THEN** 系统 SHALL 使用对应类型的正式存储或配置位置作为 materialization 目标，而不是复用 Skill 的文件路径

### Requirement: Release pipeline must block unsafe promotion
系统 SHALL 在发布前检查验证结果、门禁结果、基线版本一致性和发布后 smoke test；任一条件不满足时 SHALL 阻止版本切换。

#### Scenario: Verification gate failed
- **WHEN** 候选验证未通过门禁
- **THEN** 系统 SHALL 阻止发布并 SHALL 保持当前版本指针不变

#### Scenario: Baseline changes before publish
- **WHEN** 提案验证完成后，目标 artifact 的正式基线版本已变化
- **THEN** 系统 SHALL 要求重新验证，而不是直接发布旧候选

### Requirement: Release pipeline must support rollback with audit history
系统 SHALL 允许将 artifact 回滚到之前的已知版本，并 SHALL 保留回滚前后的版本状态、原因和操作记录。

#### Scenario: Operator rolls back a version
- **WHEN** 研发或管理员触发回滚
- **THEN** 系统 SHALL 将当前版本指针切回目标版本，并 SHALL 记录回滚原因和操作者

#### Scenario: Rollback target is invalid
- **WHEN** 用户指定了不存在或不可用的回滚版本
- **THEN** 系统 SHALL 拒绝回滚并 SHALL 保持当前版本不变

### Requirement: Release pipeline must expose publish status and version history
系统 SHALL 在管理后台和相关 API 中暴露当前版本、历史版本、发布结果和回滚结果，供研发和管理员审计。

#### Scenario: View artifact release history
- **WHEN** 用户打开某个 artifact 的版本历史
- **THEN** 系统 SHALL 返回每个版本的状态、创建者、创建时间和当前生效状态

#### Scenario: View release receipt
- **WHEN** 用户查看某次发布回执
- **THEN** 系统 SHALL 显示发布对象、发布版本、门禁结果、发布后校验结果和审批记录

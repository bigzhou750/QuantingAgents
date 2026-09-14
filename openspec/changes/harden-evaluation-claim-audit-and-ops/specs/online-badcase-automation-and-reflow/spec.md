## ADDED Requirements

### Requirement: Online Bad Case runtime configuration must be persistence-backed and versioned
线上 Bad Case 自动发现配置 MUST 以数据库记录作为运行时覆盖来源，环境变量只作为首次初始化或数据库不可用时的安全默认值；配置记录 MUST 至少包含 `config_key`、`version`、`enabled`、`enable_judge`、`soft_sample_rate`、`confidence_threshold`、`judge_threshold`、`evidence_threshold`、`max_content_length`、`status`、`updated_by`、`updated_at` 和 `change_reason`。

#### Scenario: Initial defaults are seeded from environment
- **WHEN** 系统首次初始化且数据库中没有已发布配置
- **THEN** 系统 MUST 使用环境变量生成初始默认配置，并可被后续数据库发布版本覆盖

#### Scenario: Published config overrides environment without restart
- **WHEN** 授权用户发布一版新配置
- **THEN** 线上 Bad Case Collector MUST 在无需重启服务的情况下读取新配置

### Requirement: Effective Bad Case config must be served by one validated snapshot and fail closed
线上采集和判定 MUST 通过统一的配置服务读取一份已校验的 `OnlineBadcaseConfigSnapshot`，MUST 支持短 TTL 缓存或发布后主动失效；配置读取失败 MUST 使用最近一次已发布的有效配置，若没有有效配置 MUST 回退到安全默认值并关闭自动发现，不得默认开启。

#### Scenario: Published config invalidates cache
- **WHEN** 新配置发布成功
- **THEN** 配置服务 MUST 使当前缓存失效，后续 Collector 查询返回已发布快照

#### Scenario: Config read fails
- **WHEN** 数据库读取或快照校验失败，且没有最近有效配置
- **THEN** 系统 MUST 返回 fail-closed 安全配置并关闭线上自动发现，同时记录错误原因

### Requirement: Bad Case config management must enforce permission and audit history
配置查看、编辑、发布、回滚 MUST 遵循权限边界：只有具备自进化配置管理权限的用户可以修改和发布，普通复核人员只读；每次发布 MUST 记录操作者、时间、变更原因、版本差异和生效结果，并 MUST 支持查看历史与回滚到最近有效版本。

#### Scenario: Unauthorized publish is rejected
- **WHEN** 普通复核人员调用配置发布或回滚接口
- **THEN** 系统 MUST 返回 403，且不改变当前生效配置

#### Scenario: Rollback to recent valid version
- **WHEN** 管理员选择一条历史有效配置并执行回滚
- **THEN** 系统 MUST 创建新发布版本记录本次回滚来源、原因和操作者，并让运行时读取回滚后的配置

### Requirement: Config changes must preserve existing Bad Case semantics
关闭线上自动发现或调整软信号参数只影响后续线上终态事件采集；系统 MUST NOT 删除已有 Bad Case、指标记录或人工复核结果，MUST NOT 改变硬失败、软信号、去重和回流规则，且历史样本 MUST 仍可查看和回流。

#### Scenario: Total switch is disabled
- **WHEN** 授权用户关闭 `enabled`
- **THEN** 系统 MUST 停止新建线上 Bad Case，同时保留已有 Bad Case 和指标，并允许历史记录继续查看和回流

#### Scenario: Judge switch is disabled
- **WHEN** 授权用户关闭 `enable_judge`
- **THEN** 系统 MUST 停止线上 LLM Judge 软信号但不阻断硬失败检测，并明确标记 Judge 信号未启用

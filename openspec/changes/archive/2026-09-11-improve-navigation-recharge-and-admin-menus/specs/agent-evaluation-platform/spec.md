## ADDED Requirements

### Requirement: Management access must not depend on feature enable flags

Agent 评测和自进化管理能力 SHALL 对管理员默认可用。前端 SHALL NOT 使用 `VITE_EVAL_PLATFORM_ENABLED` 或 `VITE_EVOLUTION_ENABLED` 判断页面可访问性；后端 SHALL NOT 使用 `EVAL_PLATFORM_ENABLED` 或 `EVOLUTION_ENABLED` 决定服务初始化、路由注册或接口是否可用。

#### Scenario: Backend starts without enable flags
- **WHEN** 后端启动时未配置 `EVAL_PLATFORM_ENABLED` 和 `EVOLUTION_ENABLED`
- **THEN** 评测和自进化服务 SHALL 完成初始化
- **AND** 对应 API 路由 SHALL 正常注册

#### Scenario: Admin accesses evaluation API without flags
- **WHEN** 管理员调用评测接口且未配置评测 enable 开关
- **THEN** 接口 SHALL 返回正常数据或明确的数据未初始化状态
- **AND** SHALL NOT 因“功能未启用”返回 403

#### Scenario: Admin accesses self-evolution API without flags
- **WHEN** 管理员调用自进化接口且未配置自进化 enable 开关
- **THEN** 接口 SHALL 不再依赖 enable 开关拒绝请求
- **AND** 权限判断只基于管理员角色

### Requirement: Non-admin access to evaluation APIs must remain forbidden

即使评测和自进化默认可用，普通用户 SHALL 仍然无法访问评测或自进化管理 API。

#### Scenario: Non-admin calls evaluation API
- **WHEN** 普通用户调用评测或自进化 API
- **THEN** 后端 SHALL 返回 403

#### Scenario: Evaluation API health reflects admin-only default state
- **WHEN** 管理员查看评测或自进化状态接口
- **THEN** 状态 SHALL NOT 暴露需要手工开启 enable 开关的提示
- **AND** 状态应表明该能力默认可用或仅受管理员权限约束

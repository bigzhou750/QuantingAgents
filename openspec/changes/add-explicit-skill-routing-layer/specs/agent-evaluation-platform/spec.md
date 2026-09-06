## ADDED Requirements

### Requirement: Evaluation platform must expose explicit routing strategy metrics

评测平台 MUST 支持为显式路由策略创建评测 run，并展示路由召回率、准确率、误触发率、漏触发率、静默绕过率、路由延迟和路由成本；未启用显式路由的 run MUST 将相关指标标记为 `not_configured`。

#### Scenario: Run routing strategy evaluation
- **WHEN** 管理员为指定路由策略版本创建评测 run
- **THEN** 系统保存路由候选、最终路由、Ground Truth 和评分结果

#### Scenario: Router metric not configured
- **WHEN** run 未启用显式路由
- **THEN** 评测后台显示 `not_configured`，不参与路由指标聚合

### Requirement: Evaluation trial details must show explicit routing decisions

评测 trial 详情 MUST 展示路由输入、候选 Skill、路由选中结果、未选原因、策略版本和路由耗时；旧 trial 缺少路由记录时 MUST 显示 `legacy_unverified`。

#### Scenario: View routed trial
- **WHEN** 管理员打开启用显式路由的 trial
- **THEN** 页面展示候选集、最终路由和未选原因

#### Scenario: Legacy trial without routing record
- **WHEN** trial 创建于显式路由能力上线前
- **THEN** 路由区域显示 `legacy_unverified`，其余 trace 保持可读

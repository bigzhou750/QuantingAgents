## Purpose

本能力用于保证关键功能在侧边栏和主导航中可被直接发现，避免用户已经拥有可用页面却找不到入口。对于个人投资助手和 Agent 评测这类高频入口，系统 SHALL 在登录后的主菜单中稳定展示并支持正常路由跳转。

## ADDED Requirements

### Requirement: Sidebar must expose investment and evaluation entry points
系统 MUST 在登录后的侧边栏中展示“个人投资助手”和“Agent 评测”入口，并且这些入口 MUST 能正确路由到对应页面。

#### Scenario: Navigate to investment assistant
- **WHEN** 用户点击侧边栏中的“个人投资助手”
- **THEN** 系统 SHALL 跳转到个人投资助手首页或其默认子页面

#### Scenario: Navigate to evaluation platform
- **WHEN** 用户点击侧边栏中的“Agent 评测”
- **THEN** 系统 SHALL 跳转到评测平台首页或其默认子页面

### Requirement: Sidebar menu items must be valid router targets
系统 MUST 保证侧边栏中可点击的菜单项使用有效的路由目标，不得因异常字符或格式问题导致菜单点击无效。

#### Scenario: Menu click resolves to route
- **WHEN** 用户点击侧边栏中任一显示的菜单项
- **THEN** 系统 SHALL 以可解析的路由地址完成跳转

#### Scenario: Invalid menu markup is removed
- **WHEN** 菜单项存在不可解析的标记格式
- **THEN** 系统 SHALL 将其修正为可正常渲染和点击的菜单项

## Purpose

定义算力充值页在主要导航界面中的可达入口和顶部余额交互，确保认证用户可以稳定发现并进入充值流程。

## ADDED Requirements

### Requirement: Recharge page must be reachable from main navigation surfaces

系统 SHALL 为已登录用户提供至少两个进入算力充值页的入口：侧边栏底部固定按钮和顶部右侧算力余额入口。两个入口 SHALL 都跳转到 `/token-recharge`。

#### Scenario: Sidebar bottom button
- **WHEN** 已登录用户查看侧边栏底部固定区域
- **THEN** 显示“算力充值”按钮
- **AND** 侧边栏折叠时仍保留可识别的充值图标入口
- **AND** 点击按钮后进入算力充值页

#### Scenario: Top-right balance entry
- **WHEN** 已登录用户查看顶部右侧区域
- **THEN** 显示当前算力余额
- **AND** 点击余额入口后进入算力充值页

### Requirement: Sidebar main menu must not include recharge

侧边栏主菜单 SHALL NOT 显示“算力充值”入口，避免与侧边栏底部和顶部余额入口重复。

#### Scenario: Recharge is absent from sidebar main menu
- **WHEN** 已登录用户展开侧边栏主菜单
- **THEN** 主菜单中不显示“算力充值”
- **AND** 算力充值仍可通过侧边栏底部按钮或顶部余额入口进入

### Requirement: Top-right balance must reflect current account balance

顶部右侧余额 SHALL 展示当前登录账号的算力余额，并 SHALL 在登录态建立或余额发生变化后刷新。余额获取失败时 SHALL 不影响顶部导航整体可用，并 SHALL 展示明确的不可用或空态。

#### Scenario: Balance loads successfully
- **WHEN** 顶部余额入口首次渲染且账户余额接口返回成功
- **THEN** 页面显示格式化后的当前余额

#### Scenario: Balance fetch fails
- **WHEN** 账户余额接口请求失败
- **THEN** 顶部仍保留可点击的充值入口
- **AND** 余额区域显示失败或未知状态，而不是阻塞其他顶部操作

#### Scenario: Balance updates after recharge
- **WHEN** 用户完成充值或收到余额更新事件
- **THEN** 顶部余额显示更新后的金额
- **AND** 用户无需手动刷新页面即可看到最新余额

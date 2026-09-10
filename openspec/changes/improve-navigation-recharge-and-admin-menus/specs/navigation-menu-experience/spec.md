## Purpose

定义侧边栏主菜单的稳定排序，让高频的 AI 研究能力保持在明确的第二导航位置。

## ADDED Requirements

### Requirement: AI research menu must be the second sidebar item

侧边栏主菜单 SHALL 将“AI 研究”固定在第二个位置，紧随“工作台”之后。该排序 SHALL 对所有已登录用户生效，且不因其他菜单项的可见性变化而改变相对顺序。

#### Scenario: Menu order for a normal user
- **WHEN** 普通用户展开侧边栏
- **THEN** 第一个菜单项是“工作台”
- **AND** 第二个菜单项是“AI 研究”

#### Scenario: Menu order for an administrator
- **WHEN** 管理员展开侧边栏
- **THEN** “AI 研究”仍然位于第二个位置，位于“工作台”之后
- **AND** 管理员专属菜单不得插入在“AI 研究”之前

#### Scenario: Collapsed sidebar still supports navigation
- **WHEN** 侧边栏处于折叠状态
- **THEN** “AI 研究”仍然保持第二个可点击入口
- **AND** 点击后进入 AI 研究工作台

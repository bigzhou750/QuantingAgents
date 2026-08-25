# OpenSpec 规范驱动开发流程

本项目使用 OpenSpec 实施 SDD（Spec-Driven Development，规范驱动开发）。
OpenSpec 文件是功能变更的协作契约，代码实现必须能够追溯到对应的规范和任务。

## 目录约定

```text
openspec/
├── config.yaml              # 项目上下文、语言和产物规则
├── specs/                   # 已确认的系统能力规范
└── changes/                 # 进行中和已归档的变更
```

`.agents/skills/` 中的技能由 Codex 使用，应该和 `openspec/` 一起提交。

## 标准流程

### 1. 探索问题

需求还不清楚时，先使用：

```text
$openspec-explore
```

探索阶段可以阅读代码、梳理架构和澄清边界，但不直接修改业务代码。

### 2. 创建变更提案

需求明确后，使用：

```text
$openspec-propose "用一句话描述要实现的功能或修复的问题"
```

该流程会创建一个 change，并生成：

- `proposal.md`：为什么做、做什么、不做什么
- `specs/<能力>/spec.md`：可验证的系统行为要求
- `design.md`：实现方案和技术边界
- `tasks.md`：可执行的实现任务

提案阶段只产出规范文件，不修改业务代码。

### 3. 评审规范

评审重点：

- 需求是否可验证，是否覆盖异常和边界条件
- 是否明确影响 `app/`、`tradingagents/`、`frontend/`、数据库和 API
- 是否与现有 provider、配置、权限和许可证边界兼容
- 任务是否能逐项验证并对应到规范

### 4. 按规范实现

提案评审通过后，显式启动实现流程：

```text
$openspec-apply-change
```

实现时应按 `tasks.md` 执行，同时更新任务状态。不得以“代码已经能运行”为理由跳过规范中定义的验收条件。

### 5. 验证和归档

完成实现后运行项目相关测试，并验证 OpenSpec 产物：

```bash
openspec validate --change "<change-name>"
openspec status --change "<change-name>"
```

确认测试、文档和验收条件全部完成后，使用：

```text
$openspec-archive-change
```

归档会把已确认的能力规范同步到 `openspec/specs/`，并保留变更记录。

## 变更命名

使用简短的 kebab-case 名称，例如：

```text
add-screening-export
fix-provider-fallback
improve-analysis-progress
```

## 何时必须创建 OpenSpec change

- 新增用户可见功能或 API
- 修改数据库结构、配置契约或数据源行为
- 修改智能体协作流程、分析结果格式或权限边界
- 跨模块修复，可能影响既有调用方

纯格式调整、拼写修正和不改变行为的内部重命名可以直接提交，但仍需补充必要测试。

## 与 Git 分支和 PR 的关系

建议一个 OpenSpec change 对应一个功能分支和一个 PR。PR 中应说明：

- change 名称和对应目录
- 已完成的规范和任务
- 自动化测试、手动验证结果
- 未完成项、兼容性风险和回滚方式

OpenSpec 不替代代码评审、测试或分支保护；它负责把需求、设计、实现和验收串起来。

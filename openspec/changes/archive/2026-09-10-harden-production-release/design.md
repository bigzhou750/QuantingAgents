## Context

当前代码已完成大量品牌文字迁移，但生产发布仍有构建路径、默认凭据、前端越权和发布扫描问题。See `proposal.md` for the full motivation。核心运行库仍使用 `tradingagents/` 包路径，业务代码和脚本仍通过该包导入；本设计保留该内部路径以降低迁移风险，只在产品可见层使用 zhitouagent 命名。

## Goals / Non-Goals

**Goals:**

- 让普通用户和匿名用户无法接触大模型配置、API Key 或管理员页面。
- 让生产运行时只从后端 DeepSeek 配置读取模型能力。
- 移除固定管理员密码和公开默认账号提示。
- 让生产 Compose、Docker 镜像和发布扫描达到可上线状态。

**Non-Goals:**

- 不物理重命名整个 Python 包为 `zhitouagent`。
- 不删除历史 `web/` Streamlit 源码，只从生产发布物中排除。
- 不重写模型适配器、分析算法或数据源供应商实现。

## Decisions

### D1. 保留 `tradingagents` 内部包路径，同步修正构建引用

保持 `tradingagents/` 作为核心 Python 包路径，因为 `app/`、`cli/`、测试和脚本仍大量使用 `from tradingagents import ...`。产品文案和对外标识使用 zhitouagent，但 Dockerfile SHALL 重新指向实际存在的包目录。

**Alternatives considered:**

- 物理重命名为 `zhitouagent/`：需要同步所有导入、测试夹具、脚本和数据库路径，风险高，不适合作为上线修复的一部分。
- 保留当前错误的 `COPY zhitouagent`：不可接受，会导致镜像构建失败。

### D2. 移除全局首次配置向导，不再提供前端 LLM 配置

删除 `App.vue` 对配置向导的全局调用，并从发布前端移除或停用该向导组件。配置缺失时只提示联系管理员或跳转到管理员配置页，不再要求用户填写供应商、API Key 或模型名。

分析页中的快速/深度模型选择 SHALL 对普通用户隐藏，分析请求只使用后端默认 DeepSeek 模型。管理员配置页保留为后端配置的唯一 Web 管理入口。

**Alternatives considered:**

- 保留向导但仅管理员可见：仍增加第一启动复杂度，而且无法解决普通用户入口问题，收益有限。
- 只做前端隐藏不移除逻辑：无法防止直接调用和源码内残留，失败。

### D3. 固定使用 DeepSeek 作为生产运行模型

生产环境模板与启动校验 SHALL 只要求 `DEEPSEEK_API_KEY` 和 DeepSeek 模型配置。`quick_analysis_model` 与 `deep_analysis_model` 默认值保持 `deepseek-chat` / `deepseek-reasoner`，且不得从前端请求覆盖。

管理员配置能力保留，但发布验收要求生产环境只启用 DeepSeek；其他供应商配置可作为兼容或测试能力保留在代码中，但不得进入默认发布配置。

**Alternatives considered:**

- 删除所有非 DeepSeek 适配器：影响兼容和回滚，且不属于上线必需。
- 仅靠文档约定使用 DeepSeek：无法防止错误配置，失败。

### D4. 管理员初始化改为显式受控流程

后端启动 SHALL 不再自动创建固定密码 `admin/admin123` 管理员。新建一个明确的运维命令或环境变量引导流程，要求提供密码或临时令牌；任何日志 SHALL NOT 输出明文密码。

登录页删除默认账号提示，注册入口是否开放由生产配置显式控制。

**Alternatives considered:**

- 自动生成随机密码并打印：会在日志或控制台泄露，不适合生产。
- 沿用固定密码：上线即存在已知管理员风险，不可接受。

### D5. 管理员页面同时补前端路由和页面权限

为配置管理、数据库管理、操作日志、系统日志、多数据源同步、定时任务等路由补充 `requiresAdmin`；设置页根据管理员状态决定可渲染的 tab。即使普通用户直接访问 URL，前端守卫也会拦截，后端 `get_current_admin` 继续作为最终防线。

### D6. 生产配置使用真实 Secrets，不把环境文件打进镜像

生产 Compose 和模板 SHALL 使用 `${VAR}` 引用，不提供可上线使用的默认密码；JWT/CSRF/数据库密码由部署脚本生成或在 Secrets 中维护。后端 Dockerfile 不再复制 `.env.docker` 到镜像内部，避免镜像携带开发默认凭据。

**Alternatives considered:**

- 继续在 Compose 中硬编码默认值：部署方可以暂时运行，但所有实例会共享已知凭据，不可接受。

### D7. 发布包使用显式文件清单，扫描器排除基线

发布包通过 `.dockerignore` 或 rsync 排除 `.env`、真实 Key、日志、缓存、report、`docs/release/brand-migration-baseline-scan.json` 和未交付的 Streamlit 源码。扫描器增加允许清单，区分内部包路径、第三方归属和基线报告。

## Risks / Trade-offs

- [Risk] 删除全局配置向导后，首次部署配置缺失的体验会变差。→ 配置验证页和错误提示提供清晰的管理员操作指引。
- [Risk] 保留 `tradingagents` 包名会让品牌扫描继续命中内部源码。→ 扫描器允许清单明确列出内部兼容包路径及理由。
- [Risk] 禁用非 DeepSeek 供应商可能影响正在使用旧配置的现有部署。→ 保留兼容读取和适配器，但生产新写入只允许 DeepSeek 默认配置。
- [Risk] 大量未提交的品牌迁移文件与本次修复混合，存在误改和合并风险。→ 实施前先保存当前工作区基线，以增量修复方式完成本 change，不覆盖既有修改。
- [Risk] 发布扫描基线 JSON 较大，可能被当成正式内容扫描。→ 扫描器显式排除基线文件，并只扫描正式发布树。

## Migration Plan

1. 保存当前工作区变更作为基线，记录 703 个待提交文件和 `brand-productize-zhitouagent` 的未完成状态。
2. 先修复 Docker 构建路径和 `pyproject.toml`，确保后端镜像可在干净环境构建。
3. 移除普通用户模型配置与全局向导，更新默认 DeepSeek 配置。
4. 删除固定管理员创建与登录页默认提示，加上显式初始化路径。
5. 补齐管理员路由和设置页权限，补充前端与后端权限测试。
6. 收紧生产 Compose、模板、CORS/Host 配置，替换固定凭据。
7. 调整发布扫描和排除规则，清理旧品牌与敏感文件，重新跑扫描和构建。
8. 回滚策略：每个步骤保留独立提交或 patch；若核心分析回归，回滚对应增量并保留兼容读取逻辑。

## Test Strategy

- 前端单元测试覆盖普通用户路由拦截、设置 tab 隐藏和登录页文案。
- 后端测试覆盖管理员 API 403、DeepSeek 默认模型和配置缺失错误。
- 集成测试执行前端生产构建、后端镜像构建、公开页面、普通用户分析和管理员配置主流程。
- 发布门禁执行 `scripts/validation/release_scan.py`，要求禁止项为零。

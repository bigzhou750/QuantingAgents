## Why

当前产品仍以 `TradingAgents-CN`、`TradingAgents` 和 `Vibe-Trading` 的名称、路径、文案及联系方式运行，公开可见信息不足以支持“智能投研助手 / zhitouagent”的独立产品定位，也存在原项目邮箱、仓库地址和开发环境信息残留。现在需要在保留现有投资分析与 Agent 运行能力的前提下完成产品化、审核材料补齐和发布前治理。

## What Changes

- 将产品对外品牌统一为“智能投研助手”，英文标识统一为 `zhitouagent`，更新前端标题、关于页、页脚、CLI 输出、默认文案和部署标识。
- 清理产品界面、运行时提示词、User-Agent、默认路径、环境变量、容器名、数据库/缓存/日志标识中的 `TradingAgents`、`Vibe-Trading` 和旧项目联系信息；保留 `vibe_agent_runtime` 的核心功能与兼容能力，但采用产品内部命名。
- 保持现有分析、研究、投资助手、评估和 Agent 自演进能力，不改变已有业务 API、认证权限和模型/数据源兼容契约，除非迁移需要提供兼容别名。
- 补齐无需登录即可访问的产品说明、功能定位、免责声明、隐私政策、服务条款、支持邮箱、定价/Token 计费说明及报告中的品牌和风险提示。
- 将产品支持联系方式统一为 `zh75067197@gmail.com`，移除原项目的 GitHub/Gitee 项目地址、Issue/Discussion/Star/Fork 推广入口和上游同步配置。
- 整理第三方许可证、NOTICE/归属和内部合规材料；不删除法律要求保留的版权、许可证和第三方依赖来源信息，不将第三方代码宣称为完全原创。
- 增加发布前扫描与验收机制，检查旧品牌、旧邮箱、旧项目地址、敏感配置、生产数据和构建产物是否进入发布包。

## Capabilities

### New Capabilities

- `product-identity-migration`: 定义产品品牌、运行时标识、默认文案、命名迁移和兼容策略。
- `public-review-compliance`: 定义公开产品信息、定价、隐私、服务条款、支持渠道和投资风险提示的可访问性与一致性。
- `release-origin-governance`: 定义第三方归属、旧项目痕迹清理、敏感信息扫描和发布包验收规则。

### Modified Capabilities

无。本 change 目前不修改已有 OpenSpec 能力的行为契约；现有分析、认证、配置和 Agent 能力仅进行品牌/实现层迁移，并保持兼容性。

## Impact

- **Frontend**：影响 `frontend/src` 的应用标题、关于页、页脚、公开路由、计费/文档入口和报告展示；需要保持登录、权限和现有业务路由行为。
- **Backend/runtime**：影响 `app/`、`tradingagents/`、`vibe_agent_runtime/` 的模块标识、提示词、默认值、日志、User-Agent、缓存路径和配置兼容层；核心分析流程与外部 API 契约必须保持可用。
- **Deployment/configuration**：影响 Docker、环境变量、数据库/Redis 名称、部署脚本、生产模板和构建流程；需要迁移说明与回滚策略。
- **Documentation/repository**：影响 README、部署文档、CLI、报告、历史说明和 CI 配置；第三方依赖链接与必要许可证归属保留，产品推广和上游同步内容移除。
- **Verification**：新增品牌/联系方式/URL 扫描、许可证检查、敏感信息检查、前端构建、后端测试和关键 Agent 回归测试。

## 1. Migration Inventory and Governance

- [x] 固定 Vibe-Trading 上游版本、commit、许可证和来源说明
- [x] 盘点 AgentLoop 运行时依赖闭包、tools、skills、Swarm、trace、memory、provider/config 和可选依赖
- [x] 输出迁移映射表，区分直接迁移、adapter、QuantingAgents 原有实现和明确不迁移模块
- [x] 建立迁移门禁，禁止 secrets、用户数据、runtime 产物和受限依赖进入源码

## 2. Embedded Agent Runtime

- [x] 将 session、AgentLoop、attempt、events、store 和 service 迁入内部 runtime 包
- [x] 将 trace、checkpoint、memory 和结果序列化能力迁入并接入 QuantingAgents runtime root
- [x] 将 provider/config 依赖迁入或适配到 QuantingAgents 配置体系
- [x] 将 Vibe tools、BaseTool、ToolRegistry 和自动发现机制整体迁入
- [x] 将 Vibe skills、SkillsLoader、load_skill 能力和技能目录整体迁入
- [x] 将 Swarm runtime、store、worker、preset、serialization 和 swarm tool 整体迁入
- [x] 增加启动时能力清单、导入失败和依赖缺失诊断

## 3. QuantingAgents Integration

- [x] 将研究输入框连接到内部 Agent session 和 AgentLoop facade
- [x] 统一用户 principal、session、attempt、task 和 event 上下文
- [x] 将内部 runtime 事件接入 QuantingAgents SSE 和可重放事件序列
- [x] 将 Agent task、trace、工具调用、证据、ReAct 和 Swarm 状态接入任务中心
- [x] 将高风险工具接入权限策略和 operation_logs 审计
- [x] 移除运行时对外部 Vibe source root、外部 child import 和 Vibe 独立 HTTP API 的依赖

## 4. Isolation and Runtime Storage

- [x] 将所有 session、attempt、trace、Swarm、uploads 和 artifacts 重定向到独立 runtime root
- [x] 实现用户/session 作用域校验和相对路径约束
- [x] 验证跨用户读取、路径穿越、伪造身份和越权工具调用均被拒绝
- [x] 验证 runtime root 配置不与源码目录混合，并支持部署环境覆盖

## 5. Frontend Workbench

- [x] 让研究工作台输入、历史消息、流式文本和终态结果使用内部 runtime API
- [x] 展示工具调用、工具结果、证据、ReAct、Swarm、trace 和能力不可用原因
- [x] 完成取消、重连、刷新恢复、失败重试和任务中心跳转
- [x] 增加研究工作台前端交互测试

## 6. Validation and Regression

- [x] 增加 runtime import/registry/capability inventory 测试
- [x] 增加 AgentLoop、tools、skills、Swarm 和 trace 的最小可运行测试
- [x] 增加用户隔离、权限拒绝、审计、幂等、取消和恢复测试
- [x] 增加 SSE 重连和事件顺序端到端测试
- [ ] 验证单股分析、批量分析、报告和原有任务中心回归
- [x] 使用真实配置运行一次不依赖外部 Vibe 源码路径的完整研究任务

# Agent 平台简历拆解与面试准备文档

目录：

- [0. 使用说明](#0-使用说明)
- [1. 项目总览](#1-项目总览先把边界讲清楚)
- [2. Agent Runtime 集成](#2-agent-runtime-集成)
- [3. 幻觉治理体系](#3-幻觉治理体系)
- [4. 记忆体系设计](#4-记忆体系设计)
- [5. Swarm 多智能体编排](#5-swarm-多智能体编排)
- [6. Agent 评测与治理](#6-agent-评测与治理)
- [7. Agent 自进化闭环](#7-agent-自进化闭环)
- [8. Token 成本治理](#8-token-成本治理)
- [9. 量化指标口径](#9-量化指标口径面试前必须背下来)
- [10. 通用深挖问题](#10-通用深挖问题)
- [11. 简历自检清单](#11-简历自检清单)
- [12. 后续优化方向](#12-建议补充的后续优化方向)

## 0. 使用说明

这份文档按简历里的七个能力点拆成七章，每章统一包含：

1. **简历表达可以怎么优化**：把“名词堆叠”改成“问题、方案、验证、结果”。
2. **项目具体是怎么实现的**：基于当前仓库实现整理，标注核心代码路径。
3. **面试官可能问什么**：列出常见追问、回答方向和需要补的边界。

最后补充了“量化指标口径”“通用深挖问题”和“简历自检清单”。

使用前建议做一次真实核查：不要只背文档。面试官一旦让你现场打开某段代码，或追问“这个指标分母是什么”，你需要能马上定位到对应文件。

---

## 1. 项目总览：先把边界讲清楚

### 1.1 一句话版本

基于 TradingAgents 二次开发，面向个人投资研究场景的 Agent 平台；用户通过自然语言发起研究，系统经过 AgentLoop / Swarm 执行、工具调用、证据约束、评测与受控自进化，最后通过 SSE 把过程和结果展示给用户。

### 1.2 面试前必须说清的两套执行引擎

项目里实际存在两条执行链路，建议主动区分，否则容易被面试官问穿：

- **LangGraph 链路**：原 TradingAgents 的多分析师工作流，用于单股分析、批量分析等传统图执行流程。相关实现分布在 `tradingagents/graph/`，进度回调在 `app/services/simple_analysis_service.py` 等位置。
- **AgentLoop 链路**：迁入的 Vibe Agent runtime，是自然语言研究工作台的 ReAct 主循环。核心在 `vibe_agent_runtime/vendor/src/agent/loop.py`，宿主适配在 `vibe_agent_runtime/runtime.py` 和 `app/services/vibe_agent/service.py`。

面试时可以说：

> 项目不是只用 LangGraph。传统交易分析保留 LangGraph；自然语言研究工作台使用 AgentLoop；评测平台把 Agent 执行统一抽象成 run/trial，通过 trace 适配器归一化事件。

### 1.3 项目边界

- 面向研究，不提供实盘交易建议；平台有合规表述边界。
- 只允许 Agent 操作注册过的 Skill / Prompt / Policy / Rubric / Case，不允许直接改核心代码。
- 生产默认人工审批，自进化不是无监督自动上线。

---

## 2. Agent Runtime 集成

### 2.1 简历表达优化

原始写法：

> 将 AgentLoop、Session、Tools、Skills、Trace、Checkpoint 和 Memory 等运行时能力集成到项目内部，打通自然语言输入、Agent 执行、任务状态持久化和研究结果展示链路。

建议改成：

> 将外部 Vibe Agent runtime 的完整依赖闭包迁入项目，替换原来依赖外部源码路径的 child-process 方案；通过进程内 facade 与 FastAPI 对接，保留 AgentLoop、Session、Tools、Skills、Swarm、Trace、Checkpoint、Memory，并把 Mongo/Redis/SSE/任务中心、用户隔离和权限策略接入同一链路。

如果空间允许，再加一句结果：

> 启动时输出 tools/skills/swarm preset 能力清单，工具导入失败不再静默；支持任务幂等、并发拦截、超时取消、服务重启后的孤儿任务恢复和流式 checkpoint 续传。

### 2.2 项目具体实现

代码位置：

- `vibe_agent_runtime/runtime.py`
- `vibe_agent_runtime/policy.py`
- `vibe_agent_runtime/vendor/src/agent/loop.py`
- `vibe_agent_runtime/vendor/src/session/store.py`
- `vibe_agent_runtime/vendor/src/session/checkpoint.py`
- `vibe_agent_runtime/vendor/src/agent/trace.py`
- `app/services/vibe_agent/service.py`
- `app/services/vibe_agent/paths.py`
- `app/routers/vibe_agent.py`

实现要点：

1. **源码迁入与引导**
   `EmbeddedAgentRuntime` 把 `vibe_agent_runtime/vendor` 加入运行时路径，不再依赖外部绝对路径；启动时同步项目配置里的 provider/model/API key，并注入 `EVOLUTION_SKILL_RUNTIME_ROOT`，让自进化发布后的 Skill 也能被运行时读取。

2. **进程内运行**
   API 层创建 Mongo 任务后，后台协程直接调用 `embedded_agent_runtime.run(...)`。同一 session 通过 `asyncio.Lock` 串行执行，避免两个 AgentLoop 同时写一个会话。

3. **用户/会话隔离**
   运行目录固定为：

   ```text
   <runtime_root>/users/<user_id>/sessions/<session_id>/
   ```

   `paths.py` 对 user/session id 做安全过滤，提供 `assert_within_user_scope` 和相对路径解析，防止工具把产物写到用户目录外。

4. **权限策略**
   `policy.py` 默认禁用 `bash`、`write_file`、`edit_file`、`save_skill`、`trading_place_order` 等高危工具；运行时以 `include_shell_tools=False` 构建工具注册表。面试官问安全边界时，先讲这层。

5. **任务状态**
   `VibeAgentService` 在 Mongo 写入 session/message/task/event；使用幂等 key 防止重复提交；同一用户已有 queued/processing 任务时返回 409；支持取消、超时、任务完成/失败状态更新。

6. **SSE 链路**
   Mongo 中维护事件 sequence 计数器，再把事件 publish 到 Redis channel；前端通过 `GET /api/vibe-agent/sessions/{id}/events` 消费，重连时可调用 `replay_events` 通过 `after` 游标补齐。这比只做内存 EventBus 更适合多进程部署。

7. **崩溃恢复**
   - `VibeAgentService.recover_orphaned_tasks()` 把 API 重启前仍为 queued/processing 的 Mongo 任务标记为 failed。
   - vendored `SessionService._recover_interrupted_attempts()` 把上次进程遗留的 pending/running attempt 转成终端状态，并保留 partial response。
   - `ResponseCheckpoint` 对流式回复做限频落盘，避免每个 token 都 fsync。
   - `TraceWriter` 使用 JSONL + fsync + 大文本 sidecar，大字段先原子写入再写引用记录，避免崩溃后 trace 指向不完整文件。

8. **能力清单**
   `/api/vibe-agent/capabilities` 返回内置 skill 数量、swarm preset 列表、工具数量、工具 import/registration 失败原因，便于迁移和上线诊断。

### 2.3 面试问题与回答要点

**Q1：为什么要把外部 runtime 迁进项目，不继续用 child process / PYTHONPATH？**

回答要点：外部绝对路径无法部署、版本不可控、能力边界不清晰；迁入后可以做依赖闭包、许可证边界、启动诊断、统一用户隔离和审计。child process 只是开发机上的临时桥接方案。

**Q2：LangGraph 和 AgentLoop 分别负责什么？**

回答要点：LangGraph 负责原有图式分析师流程；AgentLoop 负责自然语言 ReAct 研究；评测 runner 可以调用 Agent runtime 生成 trial。两者是不同抽象层，不需要互相替代。

**Q3：一个用户并发发两个任务会怎样？**

回答要点：API 层用幂等 key 去重；同一用户已有活动任务时返回 409；runtime 层还有 per-session lock 兜底，防止两个 loop 并发写同一 session。

**Q4：服务重启后正在跑的任务怎么办？**

回答要点：Mongo 任务层标记孤儿任务失败，让用户知道结果不可恢复；Session/Attempt 层根据 `attempt.json` 和 partial response 做恢复或显式中断；SSE 通过事件 sequence 做重放。

**Q5：这类系统最脆弱的点在哪里？**

一个比较有说服力的答案：

> 不是 LLM 本身，而是“运行时崩溃、并发、事件丢失、工具权限、状态不一致”。LLM 输出质量可以靠评测和 gate 兜底，但任务状态一旦错乱，用户会直接丢掉一次研究。

### 2.4 技术优化方向

- 把 file-based SessionStore 和 Mongo 任务状态统一到单一持久化路径，减少“文件已写、Mongo 未写”不一致窗口。
- 引入多实例部署时真正可用的分布式 session lock/任务队列，避免当前 per-process lock 在多 worker 下失效。
- 对工具注册表、SSE 吞吐、trace 写入和 cancellation 做压测，把“能力能发现”升级为“容量可评估”。

---

## 3. 幻觉治理体系

### 3.1 简历表达优化

原始写法：

> 基于正则、AST和确定性规则解析 Agent 输出，建立覆盖实体、证据、工具调用、数值一致性和安全策略校验体系。

建议改成“分两层”：

> 在运行时层建立 grounding 状态机：标的必须由工具结果锁定，价格结论必须落在本次运行观测到的 OHLC 区间，最终回答必须关联工具证据；在评测层建立 Claim-Evidence 校验，使用 AST 白名单计算、正则化报告抽查、数值交叉验证和安全规则评分，覆盖实体、证据、工具调用、数值一致性和合规边界。

如果简历里的 95%/93%/99%/1% 是真实结果，保留数字，但面试前必须把口径背下来。

### 3.2 项目具体实现

代码位置：

- `vibe_agent_runtime/vendor/src/agent/grounding.py`
- `vibe_agent_runtime/vendor/src/tools/financial_rigor_tool.py`
- `vibe_agent_runtime/vendor/src/tools/report_audit_tool.py`
- `app/services/eval/scorers/evidence_scorer.py`
- `app/services/eval/scorers/safety_scorer.py`
- `app/services/eval/scorers/trajectory_scorer.py`
- `app/services/eval/scorers/rule_scorer.py`
- `app/services/eval/metrics_service.py`

实现要点：

1. **运行时 Grounding 状态机**
   `src/agent/grounding.py` 管理三条结构性规则：
   - 使用行情数据的标的必须已经锁定身份；
   - 最终回答里的价格类数值不能与工具返回的 OHLC 区间矛盾；
   - 数值必须能追溯到本次运行中出现过的标的和工具结果。

   它不是靠 LLM 自觉，而是 AgentLoop 执行过程中可校验、可恢复的 gate。

2. **AST 白名单精确计算**
   `financial_rigor_tool.py` 对 `calc` 用 `ast.parse` + 节点白名单执行四则运算，只允许数字和 `+ - * /`，并用 `decimal.Decimal` 避免浮点误差。同时支持：
   - 市值 = 价格 × 股本校验；
   - PE/PB/ROE/P_FCF/股息率等指标推算；
   - 多数据源交叉验证，默认 2% 容差；
   - Benford 首位数统计；
   - 三情景估值。

3. **正则化报告审计**
   `report_audit_tool.py` 从 Markdown 报告里提取表格和 `label: value` 数值点，再做可复现抽样，与权威数据比较，1% 容差内通过。这回答“数值一致性”怎么落到代码。

4. **评测端 Claim-Evidence**
   `EvidenceQualityScorer` 把最终输出按句子切为 claim，再与 trace 里的 evidence/retrieval/citation 事件做 n-gram 匹配，输出 `supported / weakly_supported / unsupported / contradicted`，并保存证据片段、来源、trace event id 和预测标签。

5. **安全与工具轨迹规则**
   - `SafetyScorer` 用正则检查危险工具、敏感信息泄露、投资建议越界、无可信来源的确定性表述；
   - `TrajectoryScorer` 检查工具调用冗余、连续重复、失败率、步骤效率和多样性；
   - `RuleBasedScorer` 检查任务状态、输出存在性、耗时、token、trace、权限拒绝。

6. **幻觉检测指标**
   `MetricsService.compute_hallucination_metrics` 以 `unsupported` 和 `contradicted` 为正类，人工真值与系统预测分开保存，计算召回、精确率、F1、混淆矩阵、无证据放行率和有矛盾放行率。`weakly_supported` 默认排除，避免阈值争议污染主指标。

### 3.3 面试问题与回答要点

**Q1：金融 Agent 怎么发现幻觉？**

回答结构：

1. 先做机械可判定的部分：标的身份、价格区间、工具来源、正则安全。
2. 再做结构化证据：最终输出拆 claim，claim 对 trace evidence。
3. 最后用 LLM judge 处理语义质量。

**Q2：为什么用 AST，而不是字符串计算？**

回答要点：AST 白名单可以拒绝任意代码执行，同时支持表达式结构校验；Decimal 保证金融计算不出现 `0.1+0.2` 的浮点误差。需要说清“AST 不是用来理解自然语言，是用来安全计算算式”。

**Q3：Claim-Evidence 怎么处理中文？**

回答要点：当前实现用中文字符 n-gram（2-gram/3-gram）与证据文本做重叠；这是启发式方案，适合发现无证据 claim，不适合替代语义理解。

**Q4：Recall 95%、F1 93% 怎么证明？**

回答要点：说明评测集规模、正类定义、是否按 Claim 计算、哪些样本被 excluded、人工真值版本、scorer 版本、阈值口径。如果样本只有几十条，不要说“稳定达到”，改说“当前离线集”。

**Q5：哪些幻觉检测不到？**

能主动说边界很加分：

> n-gram 对同义改写召回有限；非价格类数值不一定全部有自动校验；需要人工真值才能算分类指标；语义幻觉最终依赖 LLM judge。

### 3.4 技术优化方向

- 用实体识别、数值抽取和语义相似度补强当前 n-gram 匹配，降低同义改写漏检。
- 把运行时 grounding gate 的判定结果统一写入评测 trace，避免线上规则和离线 scorer 口径分裂。
- 为高风险结论增加“拦截、降级、人工复核”三种动作，而不是只返回一个分数。

---

## 4. 记忆体系设计

### 4.1 简历表达优化

原始写法：

> 基于工作记忆、会话Checkpoint和跨会话PersistentMemory构建分层记忆，通过工具沉淀用户偏好与策略洞察，结合FTS5/BM25、衰减与GC，实现记忆精准召回与受控写入。

建议改成：

> 将记忆分为单次运行的 WorkspaceMemory、会话内的 Store/Checkpoint、跨会话的 PersistentMemory 三层；通过记忆工具写入用户偏好和策略洞察，用质量分、访问次数、衰减、GC 和压缩控制记忆成本。

注意：当前仓库的检索主实现是 SQLite FTS5（含 CJK unigram/bigram 扩展），不是显式 BM25 算法。如果简历里写 BM25，面试前要确认是否引入了别的检索组件，否则建议改为 `FTS5 全文检索`。

### 4.2 项目具体实现

代码位置：

- `vibe_agent_runtime/vendor/src/agent/memory.py`
- `vibe_agent_runtime/vendor/src/session/checkpoint.py`
- `vibe_agent_runtime/vendor/src/session/search.py`
- `vibe_agent_runtime/vendor/src/memory/persistent.py`
- `vibe_agent_runtime/vendor/src/memory/search_index.py`
- `vibe_agent_runtime/vendor/src/memory/hierarchy.py`
- `vibe_agent_runtime/vendor/src/memory/lifecycle.py`
- `vibe_agent_runtime/vendor/src/memory/compression.py`

实现要点：

1. **单次运行记忆**
   `WorkspaceMemory` 只保存当前 run 的 `run_dir` 和工具计数器，随 AgentLoop 生命周期结束，避免污染下个 session。

2. **会话持久化**
   `SessionStore` 以 JSONL 保存 messages，`attempt.json` 保存每次执行状态，`partial_response.json` 保存流式输出 checkpoint；`SessionSearchIndex` 用 SQLite FTS5 做跨会话全文搜索。

3. **跨会话 PersistentMemory**
   文件型 memory 带 frontmatter 元数据：`name`、`description`、`type`、`keywords`、`quality_score`、`access_count`、`last_accessed`、`compression_level`。

4. **检索**
   SQLite FTS5 建立 title/description/keywords/body 的倒排索引，并对 CJK 做 unigram + bigram 扩展，适配中文记忆。没有 FTS5 时回退到 token 扫描。

5. **质量与衰减**
   `MemoryLifecycle` 定义质量变化：
   - 任务成功 +0.1；
   - 任务失败 -0.15；
   - 用户确认 +0.2；
   - 用户拒绝 -0.3；
   - 系统来源的打分只打 7 折，防止自动反馈无限强化。

   每次 session 对同一条记忆有累计变化上限，避免一次坏反馈把正确经验写坏。

6. **GC 与压缩**
   GC 按重要度归档低价值记忆，当前默认是 archive 而不是 delete；压缩管线把长期未访问的记忆从 raw 压缩到 daily、digest，原始内容先归档再改写。

### 4.3 面试问题与回答要点

**Q1：怎么避免错误经验固化？**

回答要点：不是“记住就永久生效”。记忆受质量分、访问次数和来源可信度约束；用户确认/拒绝是最高权重；系统反馈打折；单 session 有剂量上限；低价值记忆只会归档，不会轻易删除。

**Q2：FTS5 和 BM25 有什么区别？**

回答要点：FTS5 是 SQLite 全文索引，排序逻辑依赖内置 rank；BM25 是信息检索里的排序公式。如果项目没用专门 BM25 实现，不要硬说用过；可以说“当前用 FTS5，接下来可以切换 BM25 或向量召回”。

**Q3：记忆会不会泄露其他用户数据？**

这里要诚实：当前 vendored runtime 的记忆路径基于运行 root，业务层还接入了用户维度的画像和策略上下文；但跨用户记忆隔离需要结合部署配置和权限面验证。面试时应说明你清楚这个风险。

**Q4：为什么不用 MongoDB 存记忆？**

当前文件型存储零依赖、适合本地单机；MongoDB 本身已经用于 sessions/tasks/events 元数据。如果规模上去了，可以迁移到按 user 的 Mongo 集合 + embedding 向量库。

---

## 5. Swarm 多智能体编排

### 5.1 简历表达优化

原始写法：

> 基于YAML Preset和 DAG 构建可配置的多智能体协作流程，支持专业角色分工、分层并行执行等。

建议改成：

> 用 YAML 声明 Agent 角色、工具白名单、Skill 白名单和 DAG 依赖；运行时把任务按拓扑分层并行执行，并把上游摘要注入下游角色；支持 preset 校验、失败恢复、取消和基于工具证据的防幻觉约束。

### 5.2 项目具体实现

代码位置：

- `vibe_agent_runtime/vendor/src/swarm/presets.py`
- `vibe_agent_runtime/vendor/src/swarm/models.py`
- `vibe_agent_runtime/vendor/src/swarm/runtime.py`
- `vibe_agent_runtime/vendor/src/swarm/worker.py`
- `vibe_agent_runtime/vendor/src/swarm/grounding.py`
- `vibe_agent_runtime/vendor/src/swarm/task_store.py`
- `vibe_agent_runtime/vendor/src/swarm/presets/*.yaml`

实现要点：

1. **YAML Preset**
   preset 声明 `agents`、`tasks`、`variables`、`depends_on`、`input_from` 等字段；用户 preset 目录可以被加载并覆盖内置 preset；preset name 只允许单路径段，防止路径穿越。

2. **DAG 校验与分层**
   `validate_dag` 检查环、未知 agent/task 引用；`topological_layers` 把无依赖的任务归入同一层；运行层用 `ThreadPoolExecutor` 并行执行同层任务，层间等待下游。

3. **专业角色**
   每个 agent 有 role、system_prompt、tools、skills、max_iterations、timeout、model override。例如 `investment_committee.yaml` 里有 bull advocate、bear advocate、risk officer、portfolio manager 等角色。

4. **上游上下文**
   `input_from` 把上游任务摘要注入下游 prompt；运行时用 `upstream_context` 作为内部模板变量，避免下游角色重新发明结论。

5. **防幻觉约束**
   swarm 启动前会预取用户 prompt 中识别到的 symbol 的行情数据作为 `Ground Truth block`；worker system prompt 强制要求所有具体数字来自本次工具调用、Ground Truth 或上游已经标注来源的上下文，否则不能引用训练记忆里的价格。

6. **恢复与取消**
   `start_run` 支持 `resume_from`，已完成的 task 和 artifact 可以保留，未完成任务重新执行；`cancel_run` 通过 threading.Event 通知各 worker；启动时会 reap 上一进程遗留的 stale running run。

7. **Token/成本**
   worker 优先读取 provider 返回的真实 `usage_metadata`，缺失时才用字符长度估算，并把 token 汇总写入 run。

### 5.3 面试问题与回答要点

**Q1：怎么把流程做成可配置？**

回答要点：Preset 是数据而不是代码；新增一个角色只需要加 YAML agent 和 task；上线前用 `inspect_preset` 做 dry-run 校验，能提前发现重复 id、未知依赖、模板变量缺失。

**Q2：怎么理解分层并行？**

回答要点：`topological_layers` 把 task 按依赖分层，同一层可并行，不同层按拓扑依赖执行。这是 DAG 调度，不是全量并行。

**Q3：下游 Agent 会引用上游 Agent 的幻觉数据吗？**

回答要点：用 grounding block 和 hard rule 约束“数字必须来自工具或可信上下文”；下游如果引用上游，上游必须先说明来源。但本质上这是 prompt 约束加工具白名单，不是数学证明。

**Q4：规模怎么扩展？**

当前 `ThreadPoolExecutor` 适合单机；如果要扩展，可以把 SwarmRun 改成分布式任务队列，例如 Redis/Celery，或让每个 agent 单独进 worker，而不是线程。

---

## 6. Agent 评测与治理

### 6.1 简历表达优化

原始写法：

> 基于版本化评测集和Claim-Evidence评分，持续验证Agent的结果质量与证据链，并通过BadCase回流和Release Gate发现版本回归、阻断低质量发布。

建议改成：

> 建设 run/trial 两级评测平台：创建 run 时锁定数据集版本、case 内容、scorer 配置、judge 配置和数据窗口；trial 结果落到 Mongo，trace 统一归一化；以 pass@k、pass^k、规则安全分、Claim-Evidence、LLM judge 和人工复核多维评分，支持 Bad Case 回流、趋势下钻和 Release Gate。

### 6.2 项目具体实现

代码位置：

- `app/models/eval.py`
- `app/services/eval/runner_service.py`
- `app/services/eval/trace_adapter.py`
- `app/services/eval/scorer_hub.py`
- `app/services/eval/scorers/`
- `app/services/eval/metrics_service.py`
- `app/services/eval/bad_case_service.py`
- `app/routers/eval.py`

实现要点：

1. **版本化数据集**
   `EvalDataset` / `EvalCase` 支持版本发布；创建 run 时把 case 内容、scorer 版本、judge 配置、data window 写进 `RunSnapshot`，避免金融行情/新闻/财报变化导致复盘不可靠。

2. **Trial 模型**
   同一 Case 可跑多次 trial；`pass@k` 表示 k 次至少通过一次，`pass^k` 表示 k 次全部通过。常用 trial=3/5 做稳定性评估。

3. **Trace 归一化**
   `TraceAdapter` 把 Vibe runtime 事件映射成 `llm_call / tool_call / skill_route / swarm_step / retrieval / evidence / safety_check` 等标准事件，再写入 `eval_trace_events`。

4. **Scorer Hub**
   注册规则、输出完整性、证据质量、轨迹、安全、LLM judge、DeepEval、Ragas、RedTeam 等评分器；未安装依赖显示 `not_configured`，未选择显示 `skipped`，避免被误解为低分。

5. **评分与审计**
   每条 `EvalScore` 保存 scorer_version、evidence refs、claims、reason；人工复核记录 reviewer、old/new score、action、comment，支持 approve/reject/adjust_score/add_bad_case/reflow。

6. **Bad Case 回流**
   `BadCaseService` 支持从 trial failure、human review、safety intercept、user feedback、online sampling 创建 Bad Case，再转换为正式 case 加入指定数据集。

7. **Release Gate**
   Gate 可配置成功率、pass@3、失败率、必须通过的评分器；低分、失败率和安全评分不达标时返回失败原因，阻断发布。该能力默认关闭，由管理员显式启用。

8. **观测平台**
   `ObservabilityAdapter` 支持 none / Langfuse / Phoenix；导出前对 trace 中的数据做银行卡、身份证、手机号、邮箱、凭证等脱敏，并对大文本做截断或摘要。

### 6.3 面试问题与回答要点

**Q1：怎么保证评测结果可复现？**

回答要点：run 创建时保存 dataset version、case_content snapshot、scorer_config snapshot、judge_config、data_window；候选验证只允许 validation split，不能访问 test/holdout/production split。

**Q2：pass@k 和 pass^k 的区别？**

回答要点：pass@k 更接近“存在一次成功”，适合评估覆盖率；pass^k 要求 k 次全过，适合评估稳定性。公式来自组合计数，不是简单算平均值。trial=1 时信息量低。

**Q3：为什么未启用 scorer 不能算低分？**

回答要点：`ScoreStatus` 区分 passed/failed/skipped/not_configured/error；DeepEval/Ragas 等外部评分器未安装或未启用时显示 not_configured，避免污染聚合和 Release Gate。

**Q4：Bad Case 怎么回流？**

回答要点：线上抽样或人工复核标记失败 -> 进入 Bad Case 池 -> 补充期望输出和评分标准 -> 转换为正式 case -> 加入指定数据集版本 -> 后续 run 覆盖该回归样本。

**Q5：如果模型升级后评测集通过率上升，但线上变差怎么办？**

回答要点：说明评测集可能没覆盖线上长尾；需要线上抽样回流、Bad Case 补充、Holdout 隔离、Release Gate、灰度观察和 rollback。这也是自进化闭环要解决的问题。

---

## 7. Agent 自进化闭环

### 7.1 简历表达优化

原始写法：

> 建立从失败归因、候选变更生成到隔离验证和受控发布的闭环，将线上Bad Case转化为Prompt、Skill、Policy及评测用例优化。

建议改成：

> 建立 Trigger -> Proposal -> Verify -> Approve -> Promote/Rollback 闭环：评测回退、失败聚类和 Bad Case 阈值触发候选提案；提案只允许修改受控 Artifact；候选在固定数据集和 sandbox overlay 中验证，通过质量、安全、成本、延迟、版本锁和人工审批后发布，并保留 receipt 与 rollback 能力。

### 7.2 项目具体实现

代码位置：

- `app/services/evolution/trigger_service.py`
- `app/services/evolution/clustering.py`
- `app/services/evolution/proposal_service.py`
- `app/services/evolution/artifact_registry.py`
- `app/services/evolution/verification_service.py`
- `app/services/evolution/governance_service.py`
- `app/services/evolution/approval_service.py`
- `app/services/evolution/promote_service.py`
- `app/services/evolution/receipt_service.py`
- `app/models/evolution.py`

实现要点：

1. **Trigger**
   `TriggerService` 监听 run 完成、趋势回退、Bad Case 数量和定时任务；当前趋势回退默认比较最近窗口的成功率，当前 run 失败率超过阈值也可触发。

2. **失败归因**
   `clustering.py` 按 error、scorer、source 聚类，并把评分维度映射到目标面：evidence -> grounding policy，llm_judge -> rubric，trajectory/rule -> skill，output completeness -> prompt，bad case -> case。当前是规则启发式归因，不是机器学习分类器。

3. **Proposal 与 Artifact Registry**
   提案保存触发来源、失败样本、目标 artifact、候选 diff、风险等级、预算估算、基线版本和 fingerprint。可修改对象被限制在 Skill、Prompt、Policy、Rubric、Case；核心代码、测试集、评分器定义和管理员凭证属于 forbidden target。

4. **Verify**
   verification service 建立 sandbox 和 overlay context，记录 proposal、artifact、baseline version、candidate version、dataset version；评测 runner 使用 overlay 运行候选版本，并把实际加载信息写入 `evolution.overlay.loaded` trace 事件。

5. **Gate 与审批**
   `GovernanceService` 统一执行状态转换、allowlist、change budget、验证次数、每日成本、版本锁和 stop reason；生产环境默认要求人工审批，不能因为 Agent 自己生成了 diff 就自动上线。

6. **Promote / Rollback / Receipt**
   Promote 前重新检查验证结果、Release Gate、基线版本是否变化、审批是否有效、sandbox 是否清理、smoke test 是否通过；发布或回滚都写入 receipt，保留版本历史和审计轨迹。

7. **线上反馈**
   线上 run、trace、用户反馈、Bad Case、proposal、verification 和 release receipt 通过引用字段关联，避免大对象复制，便于追踪“哪个发布版本导致了什么问题”。

### 7.3 面试问题与回答要点

**Q1：为什么不让 Agent 直接改生产 Prompt 或代码？**

回答要点：Agent 不能同时充当问题发现者、修改者和发布审批者；需要 allowlist、sandbox、固定验证集、人工 gate、change budget、版本锁、smoke test 和 rollback。

**Q2：候选版本怎么保证真的被验证了？**

回答要点：verification 创建 overlay context，runner 把 context 传入 runtime；runtime 读取 sandbox 内容并记录 loaded_files；production run 没有 overlay，只读取 active artifact。面试时不要只说“生成了 candidate”，要说“候选如何进入执行链路”。

**Q3：怎么避免对同一个问题无限生成 proposal？**

回答要点：用 proposal fingerprint 去重、active duplicate 检查、cooldown、窗口锁和每日 run/cost budget；相同失败模式聚类后生成一个提案，而不是每个 trial 生成一个。

**Q4：如何证明自进化真的有效？**

回答要点：固定同一 dataset version、同一 scorer/rubric 版本，baseline/candidate 对照回放，比较 pass@k、pass^k、grounding、judge、安全、延迟、成本和新增 regression；验证集不能被当成测试集反复调参。

**Q5：你提到 10+ Bad Case、7 个候选版本，分别怎么解释？**

建议准备一张表：Bad Case ID、失败类型、来源、对应 artifact、候选版本、验证 run、指标变化、是否发布。否则这两个数字很容易被认为是口号。

---

## 8. Token 成本治理

### 8.1 简历表达优化

原始写法：

> 记录Run/Trial级Token使用量和估算成本，通过上下文压缩、任务预算和Token超限规则进行资源控制。

建议改成：

> 在 AgentLoop 调用层统一采集 provider 返回的 input/output token，聚合到 run/trial 并估算成本；用五层上下文压缩控制长对话，用任务超时、max iterations、max tokens、每日验证预算和成本预算做资源控制；评测与自进化平台均能查看延迟、token 和成本变化。

### 8.2 项目具体实现

代码位置：

- `vibe_agent_runtime/vendor/src/agent/loop.py`
- `vibe_agent_runtime/vendor/src/swarm/worker.py`
- `app/services/eval/metrics_service.py`
- `app/services/usage_statistics_service.py`
- `app/core/config.py`
- `app/services/evolution/governance_service.py`

实现要点：

1. **调用层归因**
   `AgentLoop` 对 LLM 返回的 `usage_metadata` 做归一化，累加 input/output/total token 和调用次数，写入 run 目录的 `llm_usage.json`，同时通过 trace 事件对外暴露。

2. **运行级成本**
   eval trial 保存 `token_usage`、`latency_ms`、`cost_usd`；`MetricsService.compute_run_metrics` 聚合平均/总 token、成本、延迟分位数，供报告和 Release Gate 使用。

3. **系统级统计**
   `UsageStatisticsService` 把模型调用记录写入 Mongo `token_usage`，按 provider/model/date 聚合成本；定价来自模型配置中的输入/输出价格，按货币分桶。

4. **上下文压缩**
   AgentLoop 有五层压缩：
   - microcompact：低压力下裁剪旧工具结果；
   - context collapse：不用 LLM 的零成本折叠；
   - auto compact：超过 token threshold 后使用 LLM 结构化摘要；
   - compact tool：模型显式要求压缩；
   - iterative update：多次压缩时增量更新摘要。

   压缩时保留 recent tail 和 grounding verification 记录，避免模型在压缩后无法再校验关键数字。

5. **任务预算**
   配置里控制单任务超时、max iterations、tool timeout、LLM timeout；自进化再加入 `EVOLUTION_BUDGET_MAX_RUNS_PER_DAY`、`EVOLUTION_DAILY_COST_BUDGET_USD`、`EVOLUTION_CHANGE_BUDGET_CHARS`，预算超限会产生 stop reason。

### 8.3 面试问题与回答要点

**Q1：token 统计怎么保证准确？**

回答要点：优先使用 provider 返回的 usage metadata，缺失时才按字符长度估算；swarm worker 也遵循同一规则。要承认估算值不等于计费值，所以成本是“估算成本”。

**Q2：上下文压缩会不会丢失正确信息？**

回答要点：会，所以压缩不是简单截断。先做零成本折叠，再做结构化摘要，并保留最近 tail 和 grounding 记录；关键数值可以在需要时重新调用工具验证。

**Q3：怎么防止一次任务烧掉大量 token？**

回答要点：任务超时、max iterations、max tokens、tool timeout、并发限制、取消能力；评测和自进化另有每日 run/cost budget。若做多租户，还要加用户级日预算和告警。

**Q4：如果 provider 没有返回 usage，怎么处理？**

回答要点：fallback 估算并打标，不让 0 token 掩盖真实消耗；在指标口径里说明是估算。更好的方案是统一接入 tokenizer 或代理层计费。

---

## 9. 量化指标口径：面试前必须背下来

简历上的数字只有在能说清“分母、样本、版本、口径”时才有价值。下面给出口径建议；如果当前拿不到这些数据，宁可把简历改成“当前离线集”“内部评测”“试点场景”，也不要留着无法解释的数字。

| 指标 | 需要的口径 | 建议说法 |
| --- | --- | --- |
| 幻觉检测 recall >= 95% | 评测集大小、正类定义、按 Claim 还是 Answer 计算、excluded 样本、人工真值版本、scorer 版本 | “在 X 个带人工真值的 Claim 上，以 unsupported/contradicted 为正类，recall 达到 95%” |
| F1 >= 93% | 正负样本比例、弱支撑样本怎么处理 | “weakly_supported 默认排除；若计入，F1 会变成 ...” |
| 高风险结论拦截率 >= 99% | 高风险结论定义、拦截动作、真阳性/假阳性样本 | “高风险定义为 ...，在 ... 条样本中拦截 ... 条” |
| 无证据结论放行率 <= 1% | 分母是“真值 unsupported”还是“所有无证据 claim”，是否含 contradicted | “仅对真值为 unsupported 的 Claim，放行 1%” |
| 固定评测集通过率 85% -> 90% | 同一 dataset version、同一评分版本、pass@k 还是 pass^k、跑了几次 trial | “同版本评测集，trial=3，pass@3 从 85% 到 90%” |
| 10+ Bad Case 沉淀回归用例 | 每个 Bad Case 的来源、是否转成正式 case、发布版本 | “10 个线上 Bad Case 进入 Bad Case 池，其中 X 个转成回归用例” |
| 7 个候选版本 | 基线版本、候选版本、每个候选的验证结果 | “共验证 7 个候选 Skill/Prompt/Policy 版本，其中 X 个进入发布或回滚” |

面试官如果继续问“这个提升是不是过拟合评测集”，你要这样回答：

> 一是不动测试集，候选只允许验证集；二是同一个 dataset version 和 scorer 版本做 baseline/candidate 对比；三是加入新增 regression 检测；四是发布后做线上抽样和 rollback 能力。即便如此，单次离线提升仍不足以下结论，还需要多次运行、置信区间和线上观察。

---

## 10. 通用深挖问题

**Q1：如果让你重构，你会先做哪三件事？**

可以是：

1. 把 Agent runtime、Mongo 状态、SSE 事件之间的契约固化成明确文档和 schema，降低两端漂移；
2. 把评测集的“人工真值、数据快照、时间窗口、scorer 版本”变成硬性约束，避免不可复盘；
3. 把自进化的 overlay 从“prompt 注入”升级成真正的 artifact 加载边界，减少验证结果与生产不一致。

**Q2：这个项目最可能出现哪个线上故障？**

可以讲：

- Agent 长时间不结束：LLM 卡住或工具 hang；
- 并发生成消息顺序错乱；
- Mongo/Redis 状态与文件型 runtime 状态不一致；
- 评测数据版本漂移导致回归误判；
- 自进化写回正式 artifact 但没有真正在验证时加载 candidate。

**Q3：如何保证 LLM 输出安全？**

回答结构：工具权限白名单 -> 高危工具禁用 -> system prompt 边界 -> grounding gate -> 安全评分器 -> 人工复核 -> Release Gate -> 线上抽样。不能只说“加了 Prompt”。

**Q4：如何做灰度发布？**

回答方向：按用户/会话灰度；先 off 配置；用定时回归跑 golden set；对比 baseline/candidate 指标；线上抽样入 Bad Case；发现回退自动 rollback；发布 receipt 和版本关联。

**Q5：你在这个项目里最大贡献是什么？**

建议不要回答“写了很多接口”，而是给出一个有判断的答案：

> 我在项目里不只实现了功能，更把“Agent 能不能跑”升级成“Agent 跑得好不好、有没有证据、能不能被验证、能不能安全更新”。核心贡献是评测平台、幻觉治理和受控自进化这条治理链路。

---

## 11. 简历自检清单

提交简历或面试前，逐项勾选：

- [ ] 我把 LangGraph 和 AgentLoop 的边界说清了。
- [ ] 我能打开“用户输入到 SSE 展示”的主要代码路径。
- [ ] 我能解释 SSE 断线重连和事件 sequence。
- [ ] 我能解释 runtime 重启后的任务恢复方式。
- [ ] 我能说清 AST 在哪个场景用、为什么不是解析自然语言。
- [ ] 我能说清 Claim-Evidence 的四类 verdict。
- [ ] 我能背出幻觉检测指标的正类定义和样本口径。
- [ ] 我能讲出 PersistentMemory 从写入到检索到 GC 的完整生命周期。
- [ ] 我能解释 FTS5 和 BM25 的区别，且简历没有夸大 BM25。
- [ ] 我能画出一个 Swarm YAML 对应的 DAG 和并行层。
- [ ] 我能解释 pass@k 与 pass^k，以及 Release Gate 的阈值配置。
- [ ] 我能讲出自进化从 Trigger 到 Receipt 的每一步。
- [ ] 我能说出候选版本是“如何进入验证 run”的，而不只是生成 diff。
- [ ] 我能说清当前实现哪里只是启发式或 prompt 约束，不是严格保证。
- [ ] 我能说明 10+ Bad Case、7 个候选版本、85%->90% 的数据来源和口径。
- [ ] 我能解释 token 统计是实报还是估算，成本按什么价格计算。

---

## 12. 建议补充的后续优化方向

如果你希望在面试里显得不是“做完就结束了”，可以主动提这些下一步：

| 模块 | 当前基础 | 可以继续优化 |
| --- | --- | --- |
| Agent Runtime | 进程内 facade、session lock、SSE replay、文件 checkpoint | 分布式锁、任务队列、统一状态机、端到端容量压测 |
| 幻觉治理 | grounding、AST 白名单、正则审计、Claim-Evidence | 语义级 claim 抽取、数值/单位归一化、风险动作分级 |
| Memory | 文件型持久化、FTS5、质量分、衰减、GC | 用户级存储隔离、混合检索、记忆写入审批、召回离线评测 |
| Swarm | YAML + DAG、拓扑分层并行、上游摘要 | 分布式 worker、优先级与配额、节点级缓存、失败重试策略 |
| Eval | dataset/run/trial、snapshot、scorer hub、gate | 统计显著性、置信区间、线上采样、自动报告与 CI gate |
| Self-evolution | trigger/proposal/verify/promote/rollback | 更严格 artifact overlay、灰度发布、post-release 自动回流 |
| Token | provider usage、压缩、run/trial 成本统计 | 用户级预算、模型路由、实时成本告警、统一 tokenizer |

1. **Grounding 升级**：用更细的实体解析、数值抽取和语义相似度替换当前 n-gram，减少同义改写漏检。
2. **评测数据闭环**：把线上 Agent session 按规则自动抽样进入评测或 Bad Case 池，减少人工搬运。
3. **记忆迁移**：把文件型 PersistentMemory 迁移到按用户分区的 Mongo/Postgres，并引入 embedding 检索。
4. **自进化 Overlay 硬化**：候选 Skill/Prompt/Policy 不通过 prompt 注入，而是加载为独立 artifact 上下文，统一 verify 与 production 的读取路径。
5. **成本控制产品化**：增加用户级预算、模型路由成本预测、超限自动降级和告警。
6. **Runtime 生产化**：把 per-process lock 升级为分布式锁/队列，增加 SSE、trace、工具注册和长任务的容量压测。
7. **Swarm 生产化**：将当前单机线程池逐步拆为可恢复的分布式 task worker，并增加每个角色的配额和优先级。
8. **多环境发布**：将自进化 promote 接入 dev/test/prod Release Pipeline，每个环境都有 smoke test 和 rollback。

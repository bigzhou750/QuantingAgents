# Spec 验证报告 —— Agent 评测平台一期（add-agent-evaluation-platform）

> ⚠️ **本报告已过期（2026-08-28）**
> 报告中列出的全部 6 个缺陷均已修复，一期/二期/三期共 29 项任务已全部完成并通过 69 个测试。
> 最新状态请参考 `openspec/changes/add-agent-evaluation-platform/tasks.md`。

**Change**: add-agent-evaluation-platform
**Schema**: spec-driven
**审查范围**: 一期任务 1.1-1.10（Eval 基础设施 MVP）
**审查日期**: 2026-08-27
**审查方式**: 逐条读取真实代码 + 直接调用服务层/API/启动进程做端到端复现，而非仅凭代码"存在"判断通过

---

## ⚠️ 重要说明

本报告延续上一次（personal-investment-assistant-foundation）审查中确立的方法论：不满足于"文件/函数存在"，对每一条 MUST/MUST NOT 要求都尝试真实触发一次，包括故意构造边界条件和反向场景。审查过程中同步修复了发现的代码级 bug，每一处修复都附带复现前后的实测输出。

**结论摘要**：一期 10 个任务中，代码框架和数据模型基本齐备，但发现 **6 个真实缺陷**，其中 1 个是导致整个后端进程无法启动的致命 bug，2 个是核心执行链路上从未被跑通过的逻辑错误，1 个是权限模型完全缺失（含代码作者自己留的 TODO），1 个是"版本化重放"这一核心设计承诺在全链路上都没有实现，1 个是前端页面/路由缺失导致三类关键页面全部 404。6 处中 4 处已修复并复现验证，2 处因工作量较大记录留待后续处理。

---

## 🔴 已发现并已修复的缺陷

### 缺陷 1（致命）：`app/main.py` 引用未导入的 `eval_router`，开关打开后进程直接崩溃

**对应 Spec**：
> ### Requirement: Evaluation platform must preserve existing product workflows
> 系统 MUST 不改变现有单股分析、批量分析、任务中心和自然语言研究工作台的既有行为契约。

以及任务 1.1"验证默认关闭时不暴露评测后台 API 和页面入口"——这条要求隐含着"打开开关时功能应该正常工作"这一前提，一期任务列表和 design.md 的 Migration Plan 第 2 步明确写着"部署一期数据模型、API、runner 和后台页面"，即评测平台本身理应可用。

**复现过程**：
```bash
EVAL_PLATFORM_ENABLED=true uvicorn app.main:app ...
```
```
File "app/main.py", line 760, in <module>
    app.include_router(eval_router.router, prefix="/api/eval", tags=["evaluation"])
NameError: name 'eval_router' is not defined. Did you mean: 'sync_router'?
```

**根因**：`app/main.py` 全文没有任何 `from app.routers import eval` 或等价 import，但第 760 行（模块级顶层代码，无 try/except 包裹）直接引用了这个从未定义的名字。默认关闭（`EVAL_PLATFORM_ENABLED=False`，也是 `.env` 中未覆盖时的实际生效值）时这个 if 分支从未执行，所以此前的"看起来没问题"完全是死代码从未运行过的假象。

**修复**：在 if 分支内部做局部延迟 import：
```python
if settings.EVAL_PLATFORM_ENABLED:
    from app.routers import eval as eval_router
    app.include_router(eval_router.router, prefix="/api/eval", tags=["evaluation"])
```

**复现验证（修复后）**：
```bash
EVAL_PLATFORM_ENABLED=true uvicorn app.main:app ...
```
```
开启后 /eval 相关路径数量: 16
  /api/eval/cases/{case_id}
  /api/eval/datasets
  ... (共16个)
```
服务成功启动，16 个评测 API 全部注册。

---

### 缺陷 2（严重）：权限校验只检查"是否登录"，未校验角色，任意伪造 token 均可放行

**对应 Spec**：
> ### Requirement: Evaluation platform must expose an internal management UI
> #### Scenario: Access evaluation UI
> - **WHEN** 认证用户不具备研发或管理员权限
> - **THEN** 系统 MUST 拒绝访问评测后台页面和相关 API

**代码位置**：`app/routers/eval.py` 第 77-92 行 `verify_eval_access()`，第 86 行原文是：
```python
# TODO: 验证用户角色（研发/管理员）
# 目前先通过 Authorization header 验证登录状态
auth_header = request.headers.get("Authorization")
if not auth_header or not auth_header.startswith("Bearer "):
    raise HTTPException(status_code=401, detail="未授权访问")
return True
```
角色校验是一个**尚未实现的 TODO**，不是完成的功能。

**复现过程**：
```bash
curl -H "Authorization: Bearer any_random_token" http://localhost:8000/api/eval/datasets
```
**实测输出**：
```
{"success":true,"data":{"items":[],"count":0},"message":""}
HTTP:200
```
用一个完全随机、非真实用户的字符串作为 token，即可成功访问评测数据集接口。这不是"缺少角色维度的细粒度控制"，而是**连"token 是否对应真实用户"这一步都没有校验**，只检查了字符串前缀格式。

**已有单元测试的误导性**：`tests/test_eval_platform.py::test_eval_routes_have_access_check` 名字暗示验证了权限检查，但实际断言只是 `len(protected_routes) > 0`（除 health 外还有别的路由），完全没有验证访问控制的行为是否正确。这与上一次审查中 `terminology_compliant` 恒为 `True` 的"假绿灯"是同一类问题模式。

**处理状态**：**未修复**。原因：真正的角色校验依赖项目现有用户/角色体系的具体实现方式（如何定义"研发"、"管理员"角色，是否已有 RBAC 基础设施），修复前需要先确认项目里是否已有可复用的角色判断逻辑，避免引入一套自成一体、与现有用户体系脱节的权限模型。建议作为下一步与用户确认后专项修复，不在本次仓促处理。

---

### 缺陷 3（严重）：`_execute_trial` 引用未定义变量，Vibe runtime 可用时每个 trial 必然失败

**对应 Spec**：
> ### Requirement: Evaluation platform must execute repeated trials for each case
> 系统 MUST 支持每个 case 进行一次或多次 trial 运行，并记录每次运行的独立结果。

任务 1.4"验证单个 case 可运行"——这条验收条件在有真实 Vibe runtime 依赖的环境下完全不满足。

**复现过程**：端到端创建 dataset → case → run → start，等待执行完成，查询 trial 结果。

**修复前实测**：
```
trial_id: run_85cc28a70910_case_3956b88458a0_t0 | status: failed
error_message: name 'run_id' is not defined
```

**根因**：`app/services/eval/runner_service.py` 的 `_execute_trial(self, trial_id, case, timeout_seconds)` 函数签名里没有 `run_id` 参数，但函数体第 222-223 行使用了 `run_id` 和 `case_id` 两个从未被赋值的变量（用于构造 `eval_session_id`/`eval_task_id`）。这个 `NameError` 会在真正调用 `embedded_agent_runtime.run()` 之前就抛出，被外层 `except Exception` 捕获为失败，但失败原因是纯代码错误，不是真实的 Agent 执行结果。

**修复**：
1. 函数签名改为 `_execute_trial(self, run_id, trial_id, case, timeout_seconds)`，`case_id` 从 `case.get("case_id", "")` 里取。
2. 更新唯一的调用点：`await self._execute_trial(run_id, trial_id, case, timeout_seconds)`。

**复现验证（修复后）**：`NameError` 消失，函数能正常执行到调用 `embedded_agent_runtime.run()` 这一步（后续暴露出�connected 缺陷 4 和缺陷 5，见下）。

---

### 缺陷 4（严重）：sink 回调返回同步 `None`，与 runtime 内部协程调度机制不兼容

**代码位置**：`_execute_trial` 中原代码 `sink=lambda event_type, payload: None`。

**复现过程**：修复缺陷 3 后继续执行，暴露：
```
File "vibe_agent_runtime/runtime.py", line 257, in _on_event
    future = asyncio.run_coroutine_threadsafe(...)
TypeError: A coroutine object is required
```

**根因**：对比正常 VibeAgent 聊天路径（`app/services/vibe_agent/service.py` 第 397 行），那里传的 sink 是 `lambda event_type, payload: self.ingest_worker_event(...)`，`ingest_worker_event` 是 `async def`，调用后返回协程对象。评测 runner 里的 sink 是纯同步 lambda，调用后返回 `None`，而 runtime 内部用 `asyncio.run_coroutine_threadsafe()` 调度这个返回值，要求它必须是协程对象，传 `None` 会直接类型错误。

**修复**：把 `_noop_sink`/后续改进的 `_make_trace_sink` 都定义为 `async def`。

**复现验证（修复后）**：`TypeError: A coroutine object is required` 消失。

---

### 缺陷 5（严重，数据完整性问题）：Runtime 返回非成功状态时被无条件标记为 `COMPLETED`，真实失败被静默吞掉

**对应 Spec**：
> #### Scenario: Trial failure is preserved
> - **WHEN** 某个 trial 超时、取消、失败或返回空结果
> - **THEN** 系统 MUST 保留失败原因和相关 trace，且不得覆盖其他 trial 的结果

**这是本次审查中最隐蔽、最危险的一处发现**。修复缺陷 3/4 后，`embedded_agent_runtime.run()` 能被正常调用并返回结果，但当前环境下该次调用因为 vendor 依赖内部缺陷（`vendor/src/session/service.py` 试图 `from src.memory.persistent import ...`，但 vendor 目录里实际只有 `src/agent/memory.py`，这个模块从未真正存在——**这是第三方/vendor 运行时自身的既有缺陷，不属于本次 change 引入的问题，超出本次审查范围**）而真实执行失败，返回如下字典：
```python
{'status': 'failed', 'content': '', 'reason': "No module named 'src.memory'", 'metrics': None, 'tool_trail': [], ...}
```

原代码完全没有检查 `result.get("status")`，只要 `embedded_agent_runtime.run()` 没有抛异常、返回了任何字典，就无条件执行：
```python
await db[...].update_one({"trial_id": trial_id}, {"$set": {"status": TrialStatus.COMPLETED.value, ...}})
```
把这次真实失败的 Agent 执行误标记为 `COMPLETED`。此前该问题恰好被一个附带的 `AttributeError`（见缺陷 6）意外暴露为 `FAILED`，但那是巧合，不是设计上的正确处理——如果某次失败结果里 `metrics` 恰好是空字典而非 `None`，就不会触发这个 `AttributeError`，失败会被完全静默地误记为成功，只有 `output_data.status` 字段里诚实地留着 `"failed"`，但 trial 整体状态、`completed_trials` 统计数字都会是错的。

**修复**：显式检查 `result.get("status")`，非成功值时标记为 `TrialStatus.FAILED`，`error_message` 取自 `result.get("reason")`。

**复现验证（修复后）**：
```
trial status: failed
error_message: No module named 'src.memory'
output_data.status (来自 runtime 原始返回): failed
```
现在 trial 状态与 runtime 真实执行结果一致，失败原因可读、可诊断。

---

### 缺陷 6（中等）：`.get(key, default)` 链式调用陷阱导致 `AttributeError`

**代码位置**：`result.get("metrics", {}).get("token_usage", {})`。

**根因**：`result["metrics"]` 这个 key **存在**但值恰好是 `None`（不是缺失该 key），此时 `.get("metrics", {})` 的默认值 `{}` 不会生效（`dict.get` 的默认值只在 key 不存在时生效），实际返回 `None`，链式 `.get("token_usage", {})` 就变成了对 `None` 调用，抛 `AttributeError`。

**修复**：改为 `metrics = result.get("metrics") or {}`，用 `or` 兜底而非仅依赖 `.get` 默认值。

**复现验证**：见缺陷 5 的验证输出，`AttributeError` 不再出现。

---

## 🟡 已发现、附带真实证据、但本次未修复的缺陷

### 缺陷 7：数据集/用例"版本化"是摆设，`version` 字段从未随内容变化而更新，全链路都没有按版本过滤

**对应 Spec**：
> ### Requirement: Evaluation platform must manage versioned datasets and cases
> 系统 MUST 提供评测集、评测用例和版本管理能力，并且 MUST 能按数据集版本重放同一批 case。
> #### Scenario: Replay a dataset version
> - **WHEN** 用户选择某个数据集版本发起评测运行
> - **THEN** 系统 MUST 对该版本下的全部 case 使用相同输入和评分标准进行重放

**复现过程**：
```python
# 创建数据集，添加 case，记录此刻 version
# 后续修改 case 内容（合法操作）
# 再查 version 是否变化
```
**实测输出**：
```
创建后 version: 1.0.0
修改 case 后，dataset version 是否变化: 1.0.0 -> 1.0.0
再次查询的 case 内容: {'question': '内容已被修改 v2，和跑评测时完全不同'}
结论: case 内容确实被修改了，而 dataset_version 字段完全没变
```

**根因**：
1. `EvalDataset.version` 字段只在 `create_dataset()` 时写死为 `"1.0.0"`（`dataset_service.py`），`update_dataset()`/`update_case()` 从未递增或变更它。
2. `EvalCase` 没有版本快照概念，`update_case()` 是就地修改，历史内容不保留。
3. `runner_service.create_run()`（第 77 行）和 `_execute_run()`（第 140 行）取 case 列表时调用的都是 `dataset_service.list_cases(dataset_id, limit=1000)`，**完全没有传入或按 `dataset_version` 过滤**——`list_cases()` 方法本身也没有 `version` 参数。

**影响**：即使某次评测运行记录了 `dataset_version="1.0.0"`，用户后续编辑 case 后，"按当时版本重放"这个操作实际上会拿到被覆盖后的新内容，不是运行当时的真实输入，直接违反可复现性要求。design.md 的 Risk 章节明确写了"case 绑定时间窗口、数据快照引用和数据源版本"作为应对"评测结果依赖实时金融数据导致不可复现"风险的 Mitigation，但当前实现完全没有这个机制。

**未修复原因**：这不是一处孤立的接线遗漏，而是需要重新设计的数据模型问题（应该在编辑 case 时创建新版本快照，而不是就地覆盖），涉及模型结构变更、写入逻辑重构和查询接口扩展，工作量和风险都明显超出这次审查中的其他修复项，建议作为独立任务专项处理，需要与用户确认版本化的具体产品语义（例如：是否每次保存都自动生成新版本，还是需要用户主动"发布"一个版本）。

---

### 缺陷 8：Trace 事件类型映射表覆盖不全，生命周期事件被误分类为 `ERROR`

**代码位置**：`app/services/eval/trace_adapter.py` 第 38-59 行 `VIBE_EVENT_TYPE_MAPPING`。

**复现过程**：接线 trace sink 后（见"本次同步完成的改进"），真实运行一次评测，观察实际产生的事件类型。

**实测输出**：
```
WARNING Unknown vibe event type: message.received
WARNING Unknown vibe event type: attempt.created
WARNING Unknown vibe event type: attempt.started
WARNING Unknown vibe event type: attempt.failed
trace 事件数量: 4
```

**根因**：`VIBE_EVENT_TYPE_MAPPING` 里的键（`llm_call`、`tool_use`、`skill_route` 等）参考的似乎是"内容类"事件命名，而真实 runtime 发出的"生命周期类"事件（`message.received`、`attempt.created` 等）完全不在这个映射表里，未知类型会被兜底归类为 `TraceEventType.ERROR`（`trace_adapter.py` 第 99-102 行），导致一个正常的"任务已创建"事件在 trace 回放页面上被标记成"错误"类型，产生误导。另外发现 `ingest_worker_event()`（VibeAgent 常规聊天路径）用的事件命名（`text_delta`、`swarm_status` 等）跟这份映射表也不完全一致——项目里事实上存在至少两套不同来源、命名不统一的事件类型词表。

**影响**：事件数据本身没有丢失（4 条事件都完整落盘，包含原始 payload），只是分类标签不准确，属于体验/可读性问题，不是数据完整性问题。

**未修复原因**：要正确修复需要系统梳理 Vibe runtime 完整的事件类型清单（读 `vibe_agent_runtime/vendor` 内部事件发布源码，枚举所有可能的事件名），而不是零星补几个映射就了事，那样容易遗漏、缺乏依据。建议作为独立的小任务处理。

---

## 🔵 本次同步完成的改进（不算修 bug，但是必要的功能补全）

### 改进：Trial 执行时的事件不再被丢弃，接入 `trace_adapter` 落盘

修复前，`_execute_trial` 传给 runtime 的 `sink` 是一个把所有事件丢弃的空函数（`_noop_sink`），这意味着：

> ### Requirement: Evaluation platform must preserve standardized trace and replayability
> 系统 MUST 将 Vibe Agent runtime 的消息、LLM 调用、tool、skill、Swarm、证据、错误和最终结果保存为可回放的标准化 trace。

这条要求此前完全没有被满足——`trace_adapter.py` 里有完整的归一化和持久化逻辑，但从未被 `runner_service.py` 调用过，是典型的"工具写了但没接线"（跟上一次审查中术语过滤器的问题是同一模式）。

**改动**：新增 `_make_trace_sink(trial_id)`，把 runtime 回调的 `(event_type, payload)` 转换为 `trace_adapter.adapt_vibe_event()` 期望的字典格式（字段名从 `event_type`/`payload` 转为 `type`/`data`——这两套命名并不一致，之前从未被人验证过是否能对上），归一化后立即调用 `save_single_event()` 落盘，累加 `sequence` 保证事件顺序。

**复现验证**：见上方缺陷 8 的实测输出——事件确实被完整保存了 4 条，`trace_adapter.get_trace_events(trial_id)` 能查到。这证明"记录结构化事件序列"这条核心要求现在是真正生效的，只是事件类型标签的准确性还需要缺陷 8 的后续修复。

---

## 🟠 前端页面缺失：三类关键页面全部未实现，点击后 404

（此项为用户在审查过程中主动提出，经核实确认为真实缺陷，非本次系统性扫描中主动发现）

**对应 Spec**：
> ### Requirement: Evaluation platform must expose an internal management UI
> #### Scenario: View trial details
> - **WHEN** 研发或管理员打开某个 trial
> - **THEN** 页面 MUST 显示输入、输出、trace、分数、失败原因和复核状态

**复现过程**：
```bash
grep "path:" frontend/src/router/index.ts | grep evaluation
# 只有 3 条：/evaluation/dashboard, /evaluation/datasets, /evaluation/runs
grep "router.push" frontend/src/views/Evaluation/*.vue
# index.vue 有跳转到 /evaluation/bad-cases、/evaluation/runs/{id}
# Runs.vue 有跳转到 /evaluation/runs/{id}、/evaluation/runs/create
# Datasets.vue 有跳转到 /evaluation/datasets/{id}、/evaluation/runs/create
```

**结论**：**评测运行详情页**（`/evaluation/runs/:id`）、**评测集详情页**（`/evaluation/datasets/:id`）、**Bad Case 池**（`/evaluation/bad-cases`）——路由未注册、Vue 组件文件不存在。列表页/概览页里已经放了指向这些页面的按钮和跳转逻辑，点击后命中路由表末尾的 `NotFound` 通配符，落到 404 页面。

其中"Bad Case 池"本属于 spec 二期任务 2.9 的范畴，一期不应包含，但概览页 `index.vue` 却提前放置了一个可点击的入口卡片，制造了"功能已存在"的假象，这本身也是一处需要清理的问题（要么补上二期功能，要么先从一期页面里移除这个入口，不应该让用户点到死链接）。

**未修复原因**：详情页/创建页涉及的字段展示、交互设计（trial 列表、trace 时间线渲染、分数展示等）工作量明显超出这次代码级 bug 修复的范畴，属于前端功能开发任务，不应该在一次代码审查会话里草率地生成大量 UI 代码。建议作为任务 1.8 的补完工作单独排期。

---

## 📊 回归测试

- `pytest tests/test_eval_platform.py` → 17/17 通过，本次全部修复均无回归
- `EVAL_PLATFORM_ENABLED=true` 时服务能正常启动，16 个 `/api/eval/*` 路由全部注册

## ⚠️ 未处理的仓库状态提醒

审查过程中发现当前分支 `feat/assistant` 存在一个**未完成的合并冲突**：`app/main.py` 处于 `git status` 显示"双方修改/未合并"状态（来自合并提交 `9a8f7ac feat: 评测平台功能 add-agent-evaluation-platform 任务`）。文件内容本身没有残留冲突标记（`<<<<<<<` 等），说明冲突已在内容层面被手动解决，只是缺一步 `git add app/main.py` 来标记完成。**这是本次审查开始前就已存在的状态，不是本次修改引入的**，本报告不擅自处理这个 git 索引状态，仅如实告知，由用户自行决定是否执行 `git add` 完成合并。

---

## ✅ 结论

- 一期任务在"数据模型/API 骨架/服务类存在"的意义上确实都搭起来了，但核心执行链路（trial 真实跑通、trace 记录、失败状态判断）此前从未被端到端验证过，一旦真实调用就会在最基础的地方（变量名、协程类型、状态判断）连续出错。这些问题的共同特点是：只要真的触发一次执行路径就会暴露，但"检查文件是否存在"或"跑名字听起来很扎实的单元测试"完全发现不了。
- 权限模型和数据集版本化这两项属于 Spec 里最强调可信度、可复现性的核心要求，目前分别处于"完全缺失（带 TODO 注释）"和"字段存在但从未生效"的状态，建议作为下一步优先级最高的两项来处理。
- 前端三个关键页面缺失，是用户实际使用时最先会撞到的问题，建议尽快补齐或至少从入口页面隐藏尚未实现的跳转，避免用户以为是 bug。

---

*本报告的写作方式与上一次 personal-investment-assistant-foundation 审查保持一致：给出可复现命令、真实执行输出、根因定位和修复前后对比，不做未经验证的断言。*

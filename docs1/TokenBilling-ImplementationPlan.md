# Token 充值计费模块实施方案

## Context

项目 quanting-agent（TradingAgents-CN）是一个多智能体 A股/美股/港股 AI 分析平台，当前**没有任何支付、账户、积分/额度相关代码**。需求文档 `docs1/TokenRecharge.md` v1.6 要求在 Agent 对话流内嵌入微信支付充值功能，按后台可配比例将金额换算为 token 额度，并提供银行级交易明细。v1 范围：PC+H5、微信单渠道、积分不过期、退款延后 v2。

本方案完全贴合项目现有模式（FastAPI + MongoDB motor + Vue3 + Element Plus + Pinia Options API），以 `paper.py` 为后端模板、`PaperTrading/index.vue` 为前端模板，不引入新框架。

---

## 一、数据模型设计

### 1.1 MongoDB 集合

#### ⚠️ 金额精度规范：整数毫额度

**所有金额字段统一使用整数，单位 = 厘（0.001元）**，杜绝浮点误差累积。

| 存储值 | 展示值 | 说明 |
|--------|--------|------|
| `110000` | ¥110.000 | 余额 |
| `1` | ¥0.001 | 单次扣减（四舍五入到厘） |
| `100000` | ¥100.000 | 充值金额 |

转换规则：
- **写入DB**：`int(round(yuan * 1000))` — Python 侧用 `int`，MongoDB `$inc` 天然整数原子操作
- **读出展示**：`(val / 1000).toFixed(3)` — 前端/响应层统一格式化
- **比较运算**：`$gte` 等全部基于整数，无浮点偏差
- **订单中的 amount_cny**：也用毫额度整数存储，仅在 API 响应中转为元

#### `token_accounts` — 用户额度账户
```json
{
  "user_id": "string (unique)",
  "balance_mq": 0,             // 当前可用额度（毫额度，int）
  "frozen_mq": 0,              // 预占中待结算（毫额度，int）
  "total_recharged_mq": 0,     // 累计充值（毫额度，int）
  "total_consumed_mq": 0,      // 累计消耗（毫额度，int）
  "total_gifted_mq": 0,        // 累计赠送（毫额度，int）
  "created_at": "ISO",
  "updated_at": "ISO"
}
索引: { user_id: 1 } UNIQUE
```
> 复用 [paper.py:65-115](app/routers/paper.py#L65-L115) 的 `_get_or_create_account()` 模式，但改用 `find_one_and_update(upsert=True)` 保证原子性。字段后缀 `_mq` = milli-quota（毫额度）。

#### `token_recharge_orders` — 充值订单
```json
{
  "order_id": "RC20260826xxxx (unique)",
  "user_id": "string",
  "package_id": "pkg_100 | custom",
  "amount_mq": 100000,          // 充值金额（毫额度，int）
  "exchange_rate": 1.1,         // 下单时快照
  "quota_to_credit_mq": 110000, // amount × rate（毫额度，int）
  "gift_amount_mq": 10000,      // 赠送部分快照（毫额度，int）
  "pay_type": "NATIVE|JSAPI|MWEB",
  "wx_out_trade_no": "string",
  "wx_transaction_id": "string (callback后填入)",
  "wx_prepay_id": "string",
  "wx_code_url": "string (Native二维码)",
  "wx_mweb_url": "string (MWEB跳转)",
  "status": "pending|paid|credited|failed|expired|cancelled",
  "callback_raw": {},
  "credited_at": "ISO",
  "expire_at": "ISO (30min)",
  "ab_group": "string",
  "idempotency_key": "string",
  "created_at": "ISO",
  "updated_at": "ISO"
}
索引: { order_id: 1 } UNIQUE, { user_id: 1, created_at: -1 }, { status: 1, expire_at: 1 }
```

#### `token_transactions` — 交易流水（银行级明细）
```json
{
  "txn_id": "string (unique)",
  "user_id": "string",
  "order_id": "string (nullable)",
  "type": "recharge|consume|gift|preoccupy|settle|settle_refund",
  "direction": "in|out",
  "amount_mq": 0,              // 变动金额（毫额度，int）
  "balance_before_mq": 0,      // 变动前余额（毫额度，int）
  "balance_after_mq": 0,       // 变动后余额（毫额度，int）
  "metadata": {
    "session_id": "", "task_id": "", "model": "",
    "prompt_tokens": 0, "completion_tokens": 0,
    "real_cost_mq": 0, "consumption_ratio": 1.2
  },
  "status": "success|pending|frozen|rolled_back",
  "related_txn_id": "string (preoccupy↔settle关联)",
  "created_at": "ISO"
}
索引: { txn_id: 1 } UNIQUE, { user_id: 1, created_at: -1 }, { order_id: 1 }
```

#### `token_packages` — 充值档位配置
```json
{
  "package_id": "pkg_100",
  "name": "100元套餐",
  "amount_cny": 100.0,
  "sort_order": 3,
  "enabled": true,
  "tags": ["hot"]
}
索引: { package_id: 1 } UNIQUE, { enabled: 1, sort_order: 1 }
```
默认种子数据：20/50/100/200/500 元五档。

### 1.2 计费配置存储

存入现有 `system_configs` 集合的 `system_settings` 字典中（复用 [config_service.py:695-738](app/services/config_service.py#L695-L738) 的 `update_system_settings` 模式），新增 key：

| Key | 默认值 | 说明 |
|-----|--------|------|
| `token_exchange_rate` | 1.1 | 充值兑换率 |
| `token_consumption_ratio` | 1.2 | 消耗比率（B方案·单笔盈利） |
| `token_input_price_per_1m` | 1.0 | 输入价格 ¥/1M token |
| `token_output_price_per_1m` | 2.0 | 输出价格 ¥/1M token |
| `token_preoccupy_ratio` | 1.2 | 预占系数 |
| `token_balance_warn_threshold` | 5.0 | 余额预警阈值 |
| `token_order_expire_minutes` | 30 | 订单过期时间 |
| `wxpay_mch_id` / `wxpay_app_id` / `wxpay_api_key` / `wxpay_notify_url` | — | 微信商户配置 |

### 1.3 Pydantic 模型

新建 [app/models/token_billing.py](app/models/token_billing.py)，包含：
- `TokenAccount`, `RechargeOrderCreate`, `RechargeOrderResponse`
- `TokenTransactionRecord`, `PackageInfo`, `WxPayCallbackData`
- `TokenBillingSettings`（typed wrapper over system_settings keys）

---

## 二、后端 API 设计

新建 [app/routers/token_billing.py](app/routers/token_billing.py)，`prefix="/token-billing"`，在 [main.py:~729](app/main.py#L729) 注册。

### 端点清单

| Method | Path | 说明 | Auth | Admin |
|--------|------|------|------|-------|
| GET | `/account` | 获取/创建账户，返回余额摘要(R9) | JWT | No |
| GET | `/packages` | 列出启用的充值档位(R1) | JWT | No |
| POST | `/orders` | 创建充值订单+获取支付参数(R3/R4) | JWT | No |
| GET | `/orders/{order_id}` | 查询订单状态(R6/R12) | JWT | No |
| POST | `/orders/{order_id}/query-wx` | 主动查询微信订单状态(兜底) | JWT | No |
| POST | `/wxpay/notify` | 微信异步回调(**无auth**,签名验证) | None | No |
| GET | `/transactions` | 分页交易流水(R7/R8/R10)，支持 type/date/page/limit | JWT | No |
| GET | `/transactions/export` | CSV导出(R11, PC) | JWT | No |
| GET | `/billing-config` | 读取计费参数 | JWT | **Yes** |
| PUT | `/billing-config` | 更新计费参数+审计留痕(R13) | JWT | **Yes** |
| PUT | `/packages` | CRUD充值档位(R1) | JWT | **Yes** |

### Admin 鉴权

新建依赖函数（复用 [auth_db.py:112](app/routers/auth_db.py#L112) 已有的 `is_admin` 字段）：
```python
async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
```

### 错误码

| HTTP | 业务码 | 含义 |
|------|--------|------|
| 402 | 40201 | 额度不足 |
| 400 | 40001 | 无效档位/金额 |
| 409 | 40901 | 重复订单(幂等命中) |
| 500 | 50001 | 微信API调用失败 |

---

## 三、微信支付集成

### 3.1 服务层

新建 [app/services/wxpay_service.py](app/services/wxpay_service.py)，使用 `httpx.AsyncClient` 调用微信支付 V3 API：
- `create_native_order()` → 返回 `code_url`（PC扫码）
- `create_jsapi_order()` → 返回 JSAPI 调起参数（H5微信内）
- `create_mweb_order()` → 返回 `mweb_url`（H5微信外）
- `verify_callback_signature()` / `parse_callback()` / `query_order()`

密钥从 `system_settings` 读取，永不硬编码。

### 3.2 支付类型检测

```python
def detect_pay_type(user_agent: str) -> str:
    ua = user_agent.lower()
    if "micromessenger" in ua: return "JSAPI"
    elif any(m in ua for m in ["android", "iphone", "ipad"]): return "MWEB"
    else: return "NATIVE"
```

JSAPI 需要 openid，v1 提供 `/wx-oauth-url` 端点返回 OAuth 授权链接，前端跳转后带回 code，后端换取 openid。

### 3.3 回调处理 & 幂等

`POST /wxpay/notify` 流程：
1. 验签 → 解析 body → 提取 `out_trade_no`, `trade_state`
2. 幂等检查：`find_one({order_id})` 若已 `credited` 直接返回 200
3. 若 `SUCCESS`：`find_one_and_update({status: "pending"})` 原子更新 → 调用 `credit_quota()` → `$inc balance + total_recharged` → 插入 recharge/gift 两条 transaction → 更新订单为 `credited`
4. 5秒内返回 `{"code":"SUCCESS","message":"OK"}`
5. 入账失败则记录日志+告警，后台重试任务兜底

### 3.4 订单过期清理

在 [main.py](app/main.py) 的 APScheduler 中添加每5分钟任务，标记过期 pending 订单。

---

## 四、Token 扣减集成（VibeAgent 对话流）

### 4.1 预占策略（发消息前）

#### ⚠️ 关键事实：VibeAgent 不设 max_tokens

经代码确认，VibeAgent 调用 LLM 时**完全不传 max_tokens**（OpenAI兼容/DeepSeek/Codex/Copilot 均不设；仅 Anthropic 分支有可配项但 `.env` 未设）。单条消息最多触发 **50轮 LLM 调用**（`max_iterations=50`），实际消耗无上限约束。

因此预占按固定 token 数估算必然频繁超支。采用 **"轻预占 + 实时追扣"** 策略：

#### 预占计算

```
预占毫额度 = int(round(estimated_round_tokens × output_price_per_1m / 1e6 × consumption_ratio × preoccupy_ratio × 1000))
```

- `estimated_round_tokens` = 4096（单轮预估，非整体会话）
- 预占仅覆盖**首轮**估算，不试图覆盖全部50轮
- 默认值 ≈ `int(round(4096 × 2.0 / 1e6 × 1.2 × 1.2 × 1000))` = **12 毫额度**（¥0.012）

#### 预占执行

挂载点：[service.py:247](app/services/vibe_agent/service.py#L247) `create_message_task`

```python
# 原子操作：余额 >= 预占额才扣减
result = await db.token_accounts.find_one_and_update(
    {"user_id": user_id, "balance_mq": {"$gte": preoccupy_mq}},
    {"$inc": {"balance_mq": -preoccupy_mq, "frozen_mq": preoccupy_mq}},
    return_document=ReturnDocument.AFTER
)
if result is None:
    raise HTTPException(status_code=402, detail={...})
```

> MongoDB 原子 `$inc` + `$gte` 解决多 worker 竞态（`_message_submit_lock` 是进程内锁，跨 worker 无效）。

### 4.2 双通道扣费架构

采用 **方案B（事件驱动）为主 + 方案A（对账补偿）为辅** 的双通道设计：

```
llm_usage 事件到达
       ↓
  ┌────┴────┐
  │ 通道B   │ ← 主路径：进程内直接扣库（低延迟、零网络开销）
  │ 事件驱动 │
  └────┬────┘
       ↓ (异步/定时)
  ┌────┴────┐
  │ 通道A   │ ← 安全网：定时对账补扣/释放
  │ 对账补偿 │    覆盖事件丢失、进程崩溃、数据修复
  └─────────┘
```

| | 通道B（事件驱动） | 通道A（对账补偿） |
|---|---|---|
| **角色** | 主扣费通道（99%流量） | 安全网 / 补偿通道 |
| **触发** | 每轮 llm_usage 实时触发 | 定时任务（每5分钟）+ admin手动 |
| **场景** | 正常运行 | 事件丢失、进程崩溃重启、运营排查 |
| **幂等** | txn_id 去重 | 同一笔 txn_id 跳过已结算 |
| **Ground Truth** | 内存中的事件payload | `run_dir/llm_usage.json`（vendor持久化文件） |
| **对外暴露** | 不暴露API | `POST /api/token-billing/reconcile`（admin only） |

### 4.3 通道B：实时扣减 + 超支追扣（llm_usage 事件）

挂载点：[service.py:670](app/services/vibe_agent/service.py#L670) 事件映射字典。

**关键发现**：vendor 上游 `loop.py:1357` 已有真实 per-call token 流（`llm_usage` 事件），但当前映射字典缺失该 key，事件被丢弃为 `worker_status`。

修改：
1. 在 [models.py](app/services/vibe_agent/models.py) 的 `VibeEventType` 枚举中添加 `llm_usage`
2. 在映射字典中添加 `"llm_usage": VibeEventType.llm_usage`
3. 添加**逐轮结算 + 超支追扣**逻辑：

```python
async def _settle_llm_usage(user_id, task_id, session_id, prompt_tokens, completion_tokens):
    # 1. 计算本轮实际消耗（毫额度）
    real_cost_mq = int(round(
        (prompt_tokens * input_price / 1e6 + completion_tokens * output_price / 1e6)
        * consumption_ratio * 1000
    ))
    
    # 2. 从 frozen 中扣减；若 frozen 不够则直接从 balance 追扣
    result = await db.token_accounts.find_one_and_update(
        {"user_id": user_id},
        [
            {"$set": {
                "frozen_mq": {"$max": [{"$subtract": ["$frozen_mq", real_cost_mq]}, 0]},
                "balance_mq": {"$cond": [
                    {"$gte": ["$frozen_mq", real_cost_mq]},
                    "$balance_mq",                              # frozen够扣，balance不变
                    {"$subtract": ["$balance_mq",               # frozen不够，差额从balance追扣
                        {"$subtract": [real_cost_mq, "$frozen_mq"]}]}
                ]},
                "total_consumed_mq": {"$add": ["$total_consumed_mq", real_cost_mq]},
                "updated_at": utc_now_iso()
            }}
        ],
        return_document=ReturnDocument.AFTER
    )
    
    # 3. 检查余额是否低于阈值或已耗尽
    new_balance = result["balance_mq"]
    if new_balance <= 0:
        # 触发中途熔断（见4.5）
        ...
    elif new_balance < warn_threshold_mq:
        # 推送SSE余额预警
        ...
    
    # 4. 插入 consume transaction 流水（txn_id 幂等键）
    ...
```

#### 计费配置获取：进程内缓存

结算时需要 `consumption_ratio` / 价格等配置，采用30秒TTL进程内缓存避免每轮查DB：

```python
_billing_cache: dict = {}
_billing_cache_ts: float = 0
_CACHE_TTL = 30  # 秒

async def _get_billing_config():
    global _billing_cache, _billing_cache_ts
    now = time.time()
    if now - _billing_cache_ts > _CACHE_TTL:
        config = await config_service.get_system_config()
        ss = config.system_settings if config else {}
        _billing_cache = {
            "consumption_ratio": ss.get("token_consumption_ratio", 1.2),
            "input_price": ss.get("token_input_price_per_1m", 1.0),
            "output_price": ss.get("token_output_price_per_1m", 2.0),
            "warn_threshold_mq": int(ss.get("token_balance_warn_threshold", 5.0) * 1000),
        }
        _billing_cache_ts = now
    return _billing_cache
```

与项目现有模式一致（`runtime.py` 的 `capabilities()` 也是30秒TTL缓存）。后台改配置最多30秒后自动生效。

#### 超支场景总结

| 场景 | frozen 够扣 | frozen 不够 | 处理 |
|------|-----------|------------|------|
| 正常结算 | ✅ | — | frozen -= deduction, balance 不变 |
| 部分超支 | ❌ | balance > 0 | frozen 归零, balance -= 差额（**追扣**） |
| 完全耗尽 | ❌ | balance ≤ 0 | 追扣后 balance 为负 → 触发熔断 |

> **设计决策**：v1 允许余额短暂为负（追扣导致），不做截断/拒绝。原因：① 截断会导致 LLM 输出不完整，体验更差；② 单次超支金额极小（厘级别）；③ 通过熔断机制防止持续透支。

### 4.4 通道A：对账补偿（定时任务 + admin接口）

#### 为什么需要

1. **进程崩溃**：llm_usage 事件到了但结算未完成，worker 挂了 → frozen 永远挂着
2. **Redis pubsub 丢消息**：极端情况下事件未送达 ingest_worker_event
3. **vendor 边界case**：usage_metadata 为 None 但实际有消耗
4. **运营排查**：用户投诉扣费异常时的修复工具

#### Ground Truth

vendor 上游每轮 LLM 调用后都会将累计 token 写入 `<run_dir>/llm_usage.json`（[loop.py:68](vibe_agent_runtime/vendor/src/agent/loop.py#L68)），这是独立于事件的持久化记录，作为对账基准。

#### 定时任务（每5分钟）

```python
async def reconcile_token_usage():
    # 1. 找所有 frozen_mq > 0 且 updated_at 超过10分钟的账户（疑似僵死预占）
    stale_accounts = await db.token_accounts.find({
        "frozen_mq": {"$gt": 0},
        "updated_at": {"$lt": ten_minutes_ago_iso()}
    }).to_list(None)
    
    for account in stale_accounts:
        # 2. 找到该用户最近的任务 run_dir，读取 llm_usage.json
        # 3. 对比 llm_usage.json 累计消耗 vs token_transactions 已结算金额
        # 4. 差额 > 0 → 补扣（insert consume txn + update account）
        # 5. 差额 = 0 且 frozen > 0 → 释放 frozen 回 balance
        # 6. 记录对账日志
        ...
```

#### Admin 手动触发

`POST /api/token-billing/reconcile`（require_admin），支持指定 user_id / session_id / 时间范围进行定向对账。

### 4.5 任务终态处理：释放剩余 frozen

LLM 超时/失败/取消时不会 emit llm_usage（已确认 [loop.py:1300-1310](vibe_agent_runtime/vendor/src/agent/loop.py#L1300-L1310) 超时抛异常，不走到 emit 代码），因此预占的 frozen 不会被结算消耗。

**必须在任务终态时释放**：

挂载点：[service.py:492](app/services/vibe_agent/service.py#L492) `update_task_status`，当状态变为终态（completed/failed/cancelled）时：

```python
if status in ("completed", "failed", "cancelled"):
    # 释放该任务关联的剩余 frozen
    await db.token_accounts.find_one_and_update(
        {"user_id": user_id, "frozen_mq": {"$gt": 0}},
        {
            "$inc": {"balance_mq": task_frozen_mq, "frozen_mq": -task_frozen_mq},
            "$set": {"updated_at": utc_now_iso()}
        }
    )
    # 插入 settle_refund transaction 记录
```

> ⚠️ 需要在预占时记录 `preoccupy_txn_id` 到 task metadata 中，以便终态时精确释放对应金额，而非释放全部 frozen（可能包含其他并发任务的预占）。

### 4.6 中途熔断

余额耗尽时（`balance_mq <= 0` 且 `frozen_mq == 0`）：
1. Redis 标记 `token_balance_exhausted:{user_id}` (TTL 300s)
2. 后续 llm_usage 结算时检查该标记，若存在则跳过扣减直接熔断
3. 调用 `embedded_agent_runtime.cancel(session_id)` 停止生成
4. 推送 SSE `balance_exhausted` 事件，前端展示充值引导

### 4.4 前端集成

修改 [VibeAgent/index.vue](frontend/src/views/VibeAgent/index.vue)：
- **余额徽标**：`.capability-strip`(L15-19) 添加余额显示
- **余额不足锁定**：`.composer-lock`(L191-193) 显示充值链接
- **402 处理**：`sendMessage` catch 中捕获 402 → `ElMessageBox.confirm` → 跳转充值页
- **SSE 余额更新**：`handleEvent`(L509) 添加 `balance_update` / `balance_exhausted` 分支

修改 [request.ts](frontend/src/api/request.ts)：响应拦截器添加 402 状态处理。

---

## 五、前端页面规划

### 5.1 充值页

新建 [frontend/src/views/TokenRecharge/index.vue](frontend/src/views/TokenRecharge/index.vue)

参考 [PaperTrading/index.vue](frontend/src/views/PaperTrading/index.vue) 结构：
- Header + 余额 metric-card（参考 TokenStatistics.vue 样式）
- 档位卡片网格：展示"充X元 得Y额度（含赠Z）"(R2)
- 确认弹窗：安全背书文案(R5) + 金额明细 + "确认付款"(R4)
- 支付三态：支付中(二维码/跳转)/成功(≤3s播报)/失败(R6)
- 中断恢复：onMounted 检查 pending 订单(R12)

### 5.2 交易明细页

新建 [frontend/src/views/TokenRecharge/Transactions.vue](frontend/src/views/TokenRecharge/Transactions.vue)

参考 UsageStatistics.vue 表格模式（**修复其分页 bug**：必须传 page + limit）：
- 四宫格摘要卡：当前余额/累计充值/累计消耗/赠送汇总(R9)
- 筛选栏：类型下拉 + 日期范围
- 数据表：正确服务端分页 + 状态标签(R10/R15)
- CSV 导出按钮(R11)

### 5.3 API 模块

新建 [frontend/src/api/tokenBilling.ts](frontend/src/api/tokenBilling.ts)，`export const tokenBillingApi = {...}` 风格（同 paper.ts）。

**关键**：`createOrder` 必须传 `{ retryCount: 0 }` 防止重试导致重复下单。

### 5.4 Store

新建 [frontend/src/stores/tokenBilling.ts](frontend/src/stores/tokenBilling.ts)，Options API 风格：
- state: `balance, frozen, packages, pendingOrder`
- actions: `fetchAccount(), fetchPackages(), updateBalanceFromSSE()`

### 5.5 路由 & 菜单

- [router/index.ts](frontend/src/router/index.ts)：添加 `/token-recharge` 路由组（BasicLayout + children: '' 充值页, 'transactions' 明细页）
- [SidebarMenu.vue](frontend/src/components/Layout/SidebarMenu.vue)：在"模拟交易"后添加菜单项，导入 `Wallet` 图标

---

## 六、文件清单

### 新建文件（8个）

| # | 路径 | 说明 |
|---|------|------|
| 1 | [app/models/token_billing.py](app/models/token_billing.py) | Pydantic 模型 |
| 2 | [app/routers/token_billing.py](app/routers/token_billing.py) | API 路由 |
| 3 | [app/services/token_billing_service.py](app/services/token_billing_service.py) | 核心业务（账户/预占/结算） |
| 4 | [app/services/wxpay_service.py](app/services/wxpay_service.py) | 微信支付 V3 集成 |
| 5 | [frontend/src/api/tokenBilling.ts](frontend/src/api/tokenBilling.ts) | 前端 API 客户端 |
| 6 | [frontend/src/stores/tokenBilling.ts](frontend/src/stores/tokenBilling.ts) | Pinia Store |
| 7 | [frontend/src/views/TokenRecharge/index.vue](frontend/src/views/TokenRecharge/index.vue) | 充值页 |
| 8 | [frontend/src/views/TokenRecharge/Transactions.vue](frontend/src/views/TokenRecharge/Transactions.vue) | 交易明细页 |

### 修改文件（7个）

| # | 路径 | 修改内容 |
|---|------|----------|
| 9 | [app/main.py](app/main.py) | 注册 router(~L729)、添加索引初始化、订单过期定时任务 |
| 10 | [app/core/database.py](app/core/database.py) | `create_database_indexes()`(L347) 添加 token 集合索引 |
| 11 | [app/services/vibe_agent/service.py](app/services/vibe_agent/service.py) | llm_usage 映射(L670)、预占(L247)、结算逻辑 |
| 12 | [app/services/vibe_agent/models.py](app/services/vibe_agent/models.py) | VibeEventType 添加 llm_usage |
| 13 | [frontend/src/router/index.ts](frontend/src/router/index.ts) | 添加 token-recharge 路由 |
| 14 | [frontend/src/components/Layout/SidebarMenu.vue](frontend/src/components/Layout/SidebarMenu.vue) | 添加菜单项 |
| 15 | [frontend/src/views/VibeAgent/index.vue](frontend/src/views/VibeAgent/index.vue) | 余额显示、402处理、SSE handler |
| 16 | [frontend/src/api/request.ts](frontend/src/api/request.ts) | 402 状态拦截 |

---

## 七、实施里程碑

### M0 基础层（W1-2）
- T0.1 Pydantic 模型定义
- T0.2 token_billing_service（账户CRUD、预占/结算原子操作）
- T0.3 database.py 添加索引
- T0.4 wxpay_service（V3 API、签名、回调解析）
- T0.5 token_packages 种子数据
- T0.6 system_settings 默认计费配置
- T0.7 微信商户凭证申请 & 沙箱环境（外部依赖，尽早启动）

### M1 主流程+支付（W3-5）
- T1.1 token_billing router（account/packages/orders/notify）
- T1.2 main.py 注册 router
- T1.3 回调处理 + 幂等入账
- T1.4 前端充值页 + API + Store
- T1.5 路由 + 菜单
- T1.6 确认弹窗 + 安全背书(R4/R5)
- T1.7 支付三态 UI(R6)
- T1.8 中断挽回(R12)
- T1.9 订单过期清理任务
- T1.10 E2E 测试：PC Native 扫码流程

### M2 明细+扣减+后台（W6-8）
- T2.1 交易流水服务（双分录记录）
- T2.2 流水列表 API（正确分页）
- T2.3 CSV 导出
- T2.4 前端交易明细页
- T2.5 llm_usage 事件集成
- T2.6 余额预检
- T2.7 前端 402 处理 + 余额显示
- T2.8 SSE 余额推送
- T2.9 后台计费配置 + 审计
- T2.10 中途熔断
- T2.11 任务终态释放 frozen（completed/failed/cancelled）
- T2.12 通道A对账补偿定时任务 + admin reconcile 接口
- T2.13 埋点 8 事件(R14)

### M3 打磨+GA（W8.5-10）
- T3.1 H5 JSAPI 流程（OAuth openid）
- T3.2 余额预警 UX
- T3.3 达成率校验告警(R13)
- T3.4 A/B group 标记
- T3.5 异常标记(R10)
- T3.6 综合测试（压测、边界case）
- T3.7 安全审查
- T3.8 文档 & Runbook

---

## 八、风险与缓解

| 风险 | 严重度 | 缓解措施 |
|------|--------|----------|
| 多Worker余额竞态 | 高 | MongoDB `find_one_and_update` + `$gte` 原子操作，永不 read-then-write |
| 微信回调重复入账 | 严重 | `find_one_and_update({status:"pending"})` 幂等，仅一次成功 |
| axios重试导致重复下单 | 高 | `createOrder` 强制 `retryCount:0` + 后端 idempotency_key 去重 |
| llm_usage事件丢失 | 中 | 通道A对账补偿：定时扫描僵死frozen + 对比 llm_usage.json 补扣 |
| LLM超时后frozen未释放 | 高 | 任务终态(completed/failed/cancelled)时自动释放剩余frozen回balance |
| 微信商户审批延迟 | 高 | M0 T0.7 立即启动；开发期用沙箱环境 |
| VibeAgent 1220行单体组件 | 中 | 仅做外科手术式修改（~20行），不重构 |
| config/pricing.json被覆盖 | 中 | 计费配置存 DB system_settings，不走静态文件 |
| 两个token_usage写入者双计 | 中 | 新模块只写 token_transactions，不动旧 token_usage 集合 |
| 预占超支（不设max_tokens） | 中 | "轻预占+实时追扣"策略；允许厘级短暂负余额；熔断兜底防持续透支 |
| float精度累积误差 | 高 | 全部金额字段改为整数毫额度(milli-quota)，MongoDB `$inc` 原子操作无浮点问题 |

---

## 九、验证方案

1. **单元测试**：token_billing_service 的预占/结算/幂等入账逻辑，mock MongoDB
2. **集成测试**：微信沙箱环境完整充值流程（创建订单→模拟回调→验证到账）
3. **扣减测试**：发送 VibeAgent 消息 → 验证 llm_usage 事件触发扣减 → 验证流水记录
4. **并发测试**：多 worker 同时扣减同一用户余额 → 验证不会出现负余额
5. **前端E2E**：充值页选档→确认→支付→到账播报→明细查看→对话内余额更新
6. **边界case**：余额恰好等于预占额、订单过期后回调到达、网络断开重连后状态恢复

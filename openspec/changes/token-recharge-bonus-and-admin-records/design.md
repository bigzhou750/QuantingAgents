## Context

项目已有完整的算力计费基础：`token_accounts` 保存余额和累计充值/赠送/消耗，`token_transactions` 保存充值、消费、赠送、预占和退款流水，`credit_quota` 负责支付入账，`get_transactions` 支持用户自己的分页查询，操作日志服务已用于登录、用户管理和系统配置审计。本次改动应复用这些模块，而不是新建第二套额度账户。

## Goals / Non-Goals

**Goals:**

- 复用现有毫额度（mq）存储规范和 `token_accounts`/`token_transactions`。
- 让注册赠送、管理员充值和所有收入类交易共享同一套原子入账和流水写入路径。
- 为管理员提供可搜索、可过滤、可分页的充值记录查询，并兼容旧数据。
- 把每次运营充值和注册赠送写入操作日志，支持后台审计追溯。

**Non-Goals:**

- 不引入新的支付网关、对账系统或财务系统。
- 不做余额扣减、退款申请或管理员转账功能。
- 不改变现有支付订单、套餐、预占结算和用户端交易明细的主流程。

## Decisions

### 1. 在 TokenBillingService 增加统一额度发放方法

新增 `grant_quota` 类方法，接收用户 ID、毫额度、交易类型、来源、操作人、备注和目标用户身份信息；内部通过 `get_or_create_account` 确保账户存在，再使用 MongoDB 原子 `$inc` 更新余额与累计字段，随后写入一条交易流水并清除 Redis 余额耗尽标记。注册赠送和管理员充值都调用该方法，避免在路由层直接操作集合。

**Rationale:** 与 `credit_quota` 保持同一数据写入口，金额转换、流水生成、Redis 清理和日志口径集中维护。

**Alternative considered:** 在路由层直接更新 `token_accounts` 和插入 `token_transactions`。该方案写起来少一层，但会复制入账规则，后续金额精度或审计字段变化容易漏改，因此不采用。

### 2. 注册赠送采用账户级标记保证幂等

`token_accounts` 增加可选字段 `registration_bonus_granted`。注册赠送时先原子更新满足 `registration_bonus_granted != true` 的账户，只有更新成功才写入赠送流水。公开注册和管理员创建账号都调用同一方法。

**Rationale:** 新用户只会创建一次，但并发注册、重试或脚本补发场景仍可能出现重复赠送；账户级原子标记比“先查流水再写入”更可靠。

**Alternative considered:** 仅通过 `create_user` 返回一次来保证。该假设在重试和异常补偿下不够强，因此不采用。

### 3. 管理员充值使用独立 `admin_recharge` 交易类型

管理员后台充值写为 `type=admin_recharge`、`direction=in`，金额计入 `balance_mq` 和 `total_recharged_mq`，并在 `metadata` 中保存 `source=admin_recharge`、`operator_user_id`、`operator_username`、`username`、`email`、`reason`。用户自行支付的充值继续使用现有 `recharge` 类型。

**Rationale:** 后台充值在来源和语义上都不同于支付充值，独立类型便于筛选、展示和审计；计入累计充值是因为它确实增加了用户可使用的充值额度。

**Alternative considered:** 复用 `recharge` 或 `gift` 类型并只靠 metadata 区分。复用会污染累计口径或让后台充值与赠送混淆，筛选和前端展示也不直观，因此不采用。

### 4. 充值记录查询由后端解析关键字并补全用户身份

管理员记录接口在收到关键字时，先按用户名/邮箱查询用户 ID，再结合用户 ID、流水号、订单号、目标用户和操作人元数据构造 `$or` 查询；返回当前页后按 `user_id` 回查用户集合，把 `username` 和 `email` 补进响应 metadata，避免只依赖新交易才写入的身份字段。

**Rationale:** 旧流水可能没有用户名元数据，只有 `user_id`；后端 join 可以同时支持新旧记录，前端不用维护两套查询逻辑。

**Alternative considered:** 只搜索流水号或订单号。实现简单，但无法满足“按用户名找用户充值记录”的核心运营需求，因此不采用。

### 5. 后台入口放在用户管理和系统管理

用户管理页的每个账号增加“充值算力”操作，管理员输入金额和备注后直接入账；新增系统管理菜单“充值记录”进入后台记录页，支持关键字、类型、日期和分页搜索。用户端交易明细继续保留，并新增 `admin_recharge` 类型和来源/操作人展示。

**Rationale:** 充值动作发生在选人场景，记录查看发生在审计场景，分开入口更符合管理员工作流。

**Alternative considered:** 只在用户管理页嵌入记录表。页面会过重，且无法独立搜索跨用户记录，因此不采用。

### 6. 审计复用现有操作日志

注册赠送写入 `ActionType.USER_REGISTER`，管理员充值写入 `ActionType.USER_MANAGEMENT`；操作日志 details 保存目标用户、金额、交易 ID、操作人和备注。交易流水与操作日志分别落库，互不替代。

**Rationale:** 项目已有操作日志查看页和统一查询，新增动作直接复用可以立即获得后台审计入口。

## Risks / Trade-offs

- [Risk] 注册赠送写入失败但用户已创建，可能产生“有账号无赠送”的不一致 → Mitigation: 注册和后台建号在赠送失败时返回失败并记录错误；运营可通过管理员充值补齐，服务层保留账户级赠送标记避免补发重复。
- [Risk] 管理员双击或并发提交同一次充值，可能产生两条充值流水 → Mitigation: 前端提交后禁用按钮，后端金额变更和流水写入放在同一原子更新路径；不要求提供业务幂等键，因为每次提交代表一次明确运营动作。
- [Risk] 关键字使用正则查询在数据量大时变慢 → Mitigation: 为 `token_transactions` 建立 `user_id + created_at`、`type + created_at` 和 `order_id` 索引，后台查询固定分页大小并限制日期范围。
- [Risk] 旧流水缺少用户名/邮箱/操作人元数据 → Mitigation: 后端按 `user_id` join 用户集合补全身份；缺操作人时页面显示“未知”，不阻断查询。
- [Risk] 管理员充值和支付充值都计入累计充值，财务口径可能混淆 → Mitigation: 交易类型和 metadata.source 区分来源，后台记录页展示来源；如需财务独立统计，可按该字段过滤。

## Migration Plan

1. 先扩展 `token_billing_service.py` 和 `token_billing.py` 模型：增加统一发放方法、注册赠送标记、管理员充值请求模型和后台记录查询。
2. 在 `auth_db.py` 的公开注册和管理员创建用户路径接入注册赠送，并补充操作日志。
3. 在 `token_billing.py` 增加管理员充值接口、用户账户查询接口和充值记录查询接口，全部使用管理员依赖。
4. 前端先扩展 API 类型和用户管理充值弹窗，再新增充值记录页面、路由和侧边栏入口。
5. 为 `token_transactions` 建立查询索引，运行服务层、路由层和前端测试。
6. 后端先发布并验证新接口，再发布前端页面；旧交易记录保持可读。

**Rollback:** 移除或停用管理员充值入口和注册赠送 hook，新接口不再被前端调用；已写入的交易流水、账户余额和操作日志保留，不通过删除 MongoDB 数据回滚。

## Test Strategy

- 服务层：用现有 `_FakeDB`/`_FakeRedis` 模式覆盖注册赠送、管理员充值、余额累计、流水字段、Redis 耗尽标记清理和赠送幂等。
- 路由层：覆盖未登录 401、普通用户 403、管理员充值成功、目标不存在、归档用户、非法金额和后台记录搜索。
- 前端：补充用户管理充值弹窗和充值记录页测试，验证类型/来源展示与搜索参数；运行 `npm run type-check` 和 `vitest` 相关用例。
- 兼容性：验证旧交易记录缺少新 metadata 时仍可正常查询和展示，现有支付充值生命周期不回归。

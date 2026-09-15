## 1. 后端模型与服务

- [x] 1.1 在 `app/models/token_billing.py` 增加 `AdminRechargeRequest` 模型，校验用户名或用户 ID 二选一、金额必须为正数、备注长度受限；通过模型单元测试验证合法/非法输入（spec: Admin must be able to recharge a user's compute balance; design: 1）
- [x] 1.2 在 `app/services/token_billing_service.py` 增加统一 `grant_quota` 方法，支持注册赠送和管理员充值，按 mq 原子增加余额/累计字段、写入收入交易流水并清理 Redis 余额耗尽标记；通过服务层单元测试验证余额、流水和 Redis 清理（spec: New user registration must grant a 5 yuan compute bonus, Admin must be able to recharge a user's compute balance; design: 1, 3）
- [x] 1.3 在 `token_accounts` 账户创建/更新逻辑中支持 `registration_bonus_granted` 标记，注册赠送使用原子条件避免重复发放；通过服务层测试验证重复调用只赠送一次（spec: Registration bonus must not be granted twice; design: 2）
- [x] 1.4 为 `token_transactions` 补充 `admin_recharge` 类型和来源/操作人/备注 metadata 契约；通过模型与服务测试验证新旧类型字段兼容（spec: User transaction details must expose recharge traceability; design: 3）

## 2. 注册赠送与操作日志

- [x] 2.1 在 `app/routers/auth_db.py` 公开注册成功后调用注册赠送，注册成功响应包含赠送结果；通过 auth 路由测试验证余额 5 元和赠送流水生成（spec: Public registration grants bonus; design: 2）
- [x] 2.2 在 `app/routers/auth_db.py` 管理员创建用户成功后调用同一注册赠送逻辑；通过 auth 路由测试验证管理员创建的新账号也有赠送（spec: Admin-created account also gets bonus; design: 2）
- [x] 2.3 在 `app/models/operation_log.py` 增加 `USER_REGISTER` 操作类型，注册赠送和管理员充值分别写入操作日志，包含目标用户、金额、交易 ID、操作人和备注；通过操作日志测试验证字段落库（spec: New user registration must grant a 5 yuan compute bonus, Admin must be able to recharge a user's compute balance; design: 6）

## 3. 管理员充值与记录查询接口

- [x] 3.1 在 `app/routers/token_billing.py` 增加管理员充值接口 `POST /api/token-billing/admin/recharge`，支持按用户名或用户 ID 充值，拒绝不存在/归档用户和非法金额，并记录操作日志；通过路由测试验证成功、404、403、400/422（spec: Admin must be able to recharge a user's compute balance; design: 1, 3, 6）
- [x] 3.2 增加管理员查询单用户算力账户接口，供用户管理充值弹窗展示当前余额；通过路由测试验证管理员可见、普通用户 403（spec: Admin must be able to recharge a user's compute balance; design: 5）
- [x] 3.3 在 `app/services/token_billing_service.py` 增加管理员充值记录查询，支持用户名/邮箱/用户 ID/流水号/订单号关键字、类型和日期过滤、分页，并按 `user_id` 补全用户名和邮箱；通过服务层与路由测试验证搜索和旧记录兼容（spec: Admin recharge records must be searchable; design: 4）
- [x] 3.4 在 `app/routers/token_billing.py` 增加管理员充值记录接口 `GET /api/token-billing/admin/transactions`，使用管理员权限依赖，返回分页记录；通过路由测试验证普通用户 403（spec: Non-admin access is denied; design: 4）
- [x] 3.5 在计费模块初始化中为 `token_transactions` 建立 `user_id + created_at`、`type + created_at` 和 `order_id` 索引；通过初始化或数据库测试验证索引创建（spec: Admin recharge records must be searchable; design: Migration Plan）

## 4. 前端接入

- [x] 4.1 在 `frontend/src/api/tokenBilling.ts` 增加管理员充值、管理员账户查询和充值记录查询 API 类型与方法；通过 `npm run type-check` 验证类型（spec: Admin must be able to recharge a user's compute balance, Admin recharge records must be searchable; design: 5）
- [x] 4.2 在 `frontend/src/views/System/UserManagement.vue` 为账号增加“充值算力”操作和弹窗，填写金额、备注并展示当前余额，提交后刷新账号关联充值信息；通过前端组件测试验证弹窗提交和成功提示（spec: Admin must be able to recharge a user's compute balance; design: 5）
- [x] 4.3 新增管理员充值记录页面 `frontend/src/views/System/RechargeManagement.vue`，支持用户名/邮箱/用户 ID/流水号/订单号关键字、类型、日期范围和分页查询；通过前端测试验证搜索参数和表格展示（spec: Admin recharge records must be searchable; design: 4, 5）
- [x] 4.4 在 `frontend/src/router/index.ts` 和 `frontend/src/components/Layout/SidebarMenu.vue` 增加“充值记录”管理员路由和系统管理菜单入口；通过 `npm run test:unit` 中的导航测试验证 requiresAdmin（spec: Admin recharge records must be searchable; design: 5）
- [x] 4.5 在 `frontend/src/views/TokenRecharge/Transactions.vue` 支持 `admin_recharge` 类型及来源/操作人/备注展示，旧记录缺失字段时显示为空值或未知；通过组件测试和 type-check 验证（spec: User transaction details must expose recharge traceability; design: 3, 4）

## 5. 验证与文档

- [x] 5.1 运行 `pytest tests/test_token_billing_service.py tests/test_token_billing_router.py tests/test_token_billing_models.py` 及 auth 相关测试，验证注册赠送、管理员充值、权限和记录搜索全部通过（spec: 全部; design: Test Strategy）
- [x] 5.2 在前端运行 `npm run type-check` 和 `npm run test:unit`，验证用户管理充值弹窗、充值记录页、交易明细和导航权限相关测试通过（spec: 全部; design: Test Strategy）
- [x] 5.3 运行 `openspec validate token-recharge-bonus-and-admin-records --strict`，确认 proposal、spec、design、tasks 可被 OpenSpec 校验通过（spec: 全部; design: Test Strategy）

## Purpose

定义算力账户的运营操作契约：新用户注册赠送、管理员后台手工充值、充值记录查询和审计留痕，确保每一次额度发放都可追溯、可搜索且不破坏现有充值计费流程。

## ADDED Requirements

### Requirement: New user registration must grant a 5 yuan compute bonus

系统 SHALL 在用户注册成功或管理员创建新账号成功后，为该用户自动创建算力账户并赠送 5 元算力额度。赠送额度 SHALL 计入账户余额和累计赠送金额，SHALL 生成一条收入型交易流水，并 SHALL 写入操作日志。注册赠送逻辑失败时 SHALL 记录失败日志，且不得重复赠送。

#### Scenario: Public registration grants bonus
- **WHEN** 新用户通过公开注册接口成功注册
- **THEN** 系统为该用户创建算力账户
- **AND** 账户余额增加 5.0 元
- **AND** 交易明细中出现一条方向为收入、类型为赠送的记录
- **AND** 操作日志中出现包含该用户名和赠送金额的注册赠送记录

#### Scenario: Admin-created account also gets bonus
- **WHEN** 管理员在后台成功创建新账号
- **THEN** 该新账号同样获得 5.0 元注册赠送
- **AND** 赠送记录可关联到新账号

#### Scenario: Registration bonus must not be granted twice
- **WHEN** 同一用户账号被重复作为新用户处理
- **THEN** 系统不得再次写入 5.0 元赠送交易
- **AND** 账户余额不得重复增加该赠送金额

### Requirement: Admin must be able to recharge a user's compute balance

系统 SHALL 提供仅管理员可用的充值接口，管理员 SHALL 能通过用户名或用户 ID 指定目标用户，并输入正数金额和备注。系统 SHALL 将金额按 1000 毫额度/元换算后原子增加目标用户余额，SHALL 记录一条收入型管理员充值流水，并 SHALL 写入包含操作人、目标用户、金额和备注的操作日志。

#### Scenario: Admin recharge succeeds
- **WHEN** 管理员输入有效用户名或用户 ID 和正数金额并提交
- **THEN** 目标用户算力余额按输入金额增加
- **AND** 充值记录中显示操作人、目标用户、金额和备注
- **AND** 操作日志记录本次管理员充值

#### Scenario: Recharge target not found
- **WHEN** 管理员提交的用户名或用户 ID 不存在
- **THEN** 系统返回 404
- **AND** 不增加任何账户余额
- **AND** 不生成交易流水

#### Scenario: Recharge target is archived
- **WHEN** 管理员尝试给已归档账号充值
- **THEN** 系统拒绝充值
- **AND** 不生成交易流水

#### Scenario: Invalid amount
- **WHEN** 管理员提交金额为空、小于等于 0 或超出允许上限
- **THEN** 系统返回 400 或 422
- **AND** 不修改账户余额

### Requirement: Admin recharge records must be searchable

系统 SHALL 提供仅管理员可用的充值记录查询接口，按分页返回收入类交易记录。管理员 SHALL 能按用户名、邮箱、用户 ID、流水号或订单号搜索，并 SHALL 能按类型和日期范围过滤。搜索结果 SHALL 显示用户、交易类型、金额、余额、操作人、备注、关联订单和时间。

#### Scenario: Search by username
- **WHEN** 管理员在充值记录页输入用户名并查询
- **THEN** 系统返回该用户名下匹配的收入类交易记录
- **AND** 结果按时间倒序分页展示

#### Scenario: Search by user ID or transaction ID
- **WHEN** 管理员输入完整或部分用户 ID、流水号或订单号
- **THEN** 系统返回文本匹配的记录

#### Scenario: Filter by type and date range
- **WHEN** 管理员选择充值类型并指定开始和结束时间
- **THEN** 系统只返回满足类型和日期范围的记录

#### Scenario: Non-admin access is denied
- **WHEN** 普通用户请求管理员充值或充值记录查询接口
- **THEN** 系统返回 403
- **AND** 不暴露其他用户的交易数据

### Requirement: User transaction details must expose recharge traceability

用户交易明细 SHALL 兼容现有充值、消费、赠送、预占和退款类型，并 SHALL 能识别管理员充值记录。展示管理员充值或注册赠送时 SHALL 显示来源、操作人、备注等可追溯元数据；缺少新元数据的旧记录 SHALL 保持可读，不因缺少字段而报错。

#### Scenario: User sees admin recharge metadata
- **WHEN** 已登录用户查看自己的交易明细且存在管理员充值记录
- **THEN** 页面显示该记录的类型和可见来源信息
- **AND** 若记录含操作人和备注，则一并展示

#### Scenario: Legacy transaction remains readable
- **WHEN** 用户交易明细中存在没有来源或操作人元数据的历史记录
- **THEN** 页面仍正常展示该记录
- **AND** 缺失字段显示为空值或未知，不阻断页面加载

## Purpose

为每个账号提供独立的 Agent 会话、工作区、运行产物、短期任务状态、搜索索引和长期记忆，使上下文构建和记忆召回不会把一个用户的投资偏好、对话内容或工具结果提供给另一个用户。

## ADDED Requirements

### Requirement: 会话和文件命名空间
Agent session、workspace、run、trace、上传文件和导出文件 MUST 位于包含不可变用户范围的服务端路径或存储键中；用户只能列举、读取、更新和删除自己的对象，文件路径 MUST 防止目录穿越和符号链接逃逸。

#### Scenario: 跨用户 session 访问
- **WHEN** 用户 B 提供用户 A 的 session id 或猜测其文件路径
- **THEN** 系统拒绝访问且不返回消息、文件名、标题或时间等侧信道信息

### Requirement: 短期状态和长期记忆隔离
内存任务状态、Agent workspace memory、persistent memory 的读、写、更新、删除、召回和统计 MUST 带用户范围；用户 A 的自然语言请求、工具结果和记忆摘要 SHALL NEVER 出现在用户 B 的上下文中。相同 session id 在不同用户范围下 MUST 视为不同资源或被拒绝。

#### Scenario: 记忆召回隔离
- **WHEN** 用户 B 使用与用户 A 相同或相关的查询词进行 Agent 对话
- **THEN** 召回结果只能来自 B 的记忆和当前会话，不能通过摘要、排序、计数或错误信息泄露 A 的记忆

#### Scenario: 记忆写入和删除
- **WHEN** 用户 A 保存或删除一条长期记忆
- **THEN** 只改变 A 的记忆命名空间、索引和统计，B 的同名记忆不受影响

### Requirement: 搜索索引和重建安全
会话全文搜索索引、持久化记忆索引和重建任务 MUST 保存用户范围并在查询时强制过滤；重建、清理和导入操作 MUST 不能把一个用户目录扫描到另一个用户索引。

#### Scenario: 索引查询
- **WHEN** 用户搜索自己的历史会话
- **THEN** 搜索结果仅包含其 owner 范围内的会话和消息，且分页总数也按该范围计算

### Requirement: Agent 调用身份传递
Agent runtime、工具调用和异步回调 MUST 接收服务端生成的用户上下文；任何来自提示词、请求 body、profile 字段或工具参数的用户身份声明 SHALL 不能改变租户范围。没有用户上下文的持久化操作 MUST 失败并可观测。

#### Scenario: 缺少身份的记忆操作
- **WHEN** runtime 尝试在没有用户范围的上下文中保存、召回或删除持久记忆
- **THEN** 操作失败并记录诊断事件，不降级到全局或 `admin` 存储

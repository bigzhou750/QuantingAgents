# A/B 多账号隔离测试矩阵

目标：A/B 两账号对私有资源的列表、详情、创建、更新、删除、导出、搜索、统计均不能互相访问。

| 资源 | 创建 | 列表 | 详情 | 更新 | 删除 | 搜索/统计 | 验证测试 |
|---|---|---|---|---|---|---|---|
| 自选股 | 服务端写入 user_id | A/B 各自查询 | - | - | owner 过滤删除 | - | test_personal_resource_isolation.py |
| 通知 | user_id 写入 | A/B 各自列表 | mark_read 校验 owner | - | - | unread_count 按 owner | test_personal_resource_isolation.py |
| 观察标的 | user_id 写入 | user_id 过滤 | observation_id+user_id | user_id 过滤 | - | total 按 user_id | test_personal_resource_isolation.py |
| 策略 | user_id 写入 | user_id 过滤 | strategy_id+user_id | user_id 过滤 | user_id 过滤 | - | test_personal_resource_isolation.py |
| 用户标签 | user_id 写入 | user_id 过滤 | - | user_id 过滤 | user_id 过滤 | - | test_personal_resource_isolation.py |
| 分析任务/报告 | 服务端写入 user_id | owner 过滤 | task_id+owner | 状态更新校验 | owner 过滤 | 统计按 owner | test_analysis_task_ownership.py |
| 队列任务 | owner_id+user | user 过滤 | user 过滤 | cancel 校验 | ack 校验 | - | test_analysis_task_ownership.py, test_queue_owner_cross_process.py |
| 实时通道 | token user_id | - | SSE/WS 订阅校验 | 通知定向投递 | 断开清理 | - | test_sse_and_worker_config.py, test_websocket_auth.py, test_realtime_channel_isolation.py |
| 持久记忆 | 用户目录 | - | recall 按用户目录 | - | remove 按用户目录 | stats 按用户目录 | test_scoped_persistent_memory.py |
| 用户 Skills | 用户 skills 目录 | - | A 不加载 B | patch/delete 用户目录 | - | - | test_scoped_skills.py |
| 配置/数据库/日志 | 仅管理员 | 仅管理员 | 仅管理员 | 仅管理员 | 仅管理员 | 仅管理员 | test_admin_router_access.py |

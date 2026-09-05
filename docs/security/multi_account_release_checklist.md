# 多账号隔离发布清单

## 自动检查

- [ ] `pytest -q tests/test_auth_lifecycle.py tests/test_auth_admin_routes.py`
- [ ] `pytest -q tests/test_analysis_task_ownership.py tests/test_personal_resource_isolation.py`
- [ ] `pytest -q tests/test_websocket_auth.py tests/test_realtime_channel_isolation.py`
- [ ] `pytest -q tests/test_static_tenant_audit.py`
- [ ] `npm run type-check`
- [ ] `npm run build`
- [ ] `npm run test:unit`

## 真实依赖检查

在隔离的 MongoDB database 和 Redis DB 上运行：

```bash
MONGODB_DATABASE_SCOPE=explicit \
MONGODB_DATABASE=quantingagents_iso_test \
REDIS_DB=15 \
RUN_LIVE_ISOLATION_TESTS=1 \
pytest -q tests/test_live_isolation_integration.py
```

检查项包括：A/B Mongo 查询、Redis 队列 owner、Token jti 轮换与重放、每用户 persistent memory 和清理。

## 发布门禁

1. dry-run 报告中的 `missing`、`conflicts` 和 `isolated` 已人工确认。
2. 备份可读取，且回滚只删除迁移版本簿记，不删除 owner 或隔离集合。
3. 静态扫描没有硬编码身份、无 scope 持久化或普通用户访问运维配置的结果。
4. `MULTI_ACCOUNT_ISOLATION_ENFORCE=true` 且 `MULTI_ACCOUNT_MIGRATION_VERSION` 为正数。
5. A/B 越权矩阵、前端认证测试和真实依赖集成测试全部通过。

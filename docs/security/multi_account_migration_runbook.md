# 多账号隔离迁移运行手册

## 前置条件

- MongoDB 已备份用户相关集合和 `USER_RUNTIME_ROOT`。
- `MULTI_ACCOUNT_ISOLATION_ENFORCE=false`，先执行 dry-run 和抽样确认。
- `MULTI_ACCOUNT_MIGRATION_VERSION` 与迁移脚本使用同一版本号。

## 迁移步骤

1. 运行 dry-run，检查 `mapped`、`missing`、`conflicts` 和 `isolated` 数量。
2. 备份原数据，确认隔离集合不包含可恢复业务内容。
3. 执行 `apply_migration(..., version=N)`，幂等写入 owner 并记录 `migration_versions`。
4. 开启 `MULTI_ACCOUNT_ISOLATION_ENFORCE=true`，运行 A/B 越权验收。
5. 只有验收通过后才更新部署清单中的 `MULTI_ACCOUNT_MIGRATION_VERSION`。

## 回滚

```bash
python app/scripts/rollback_user_ownership.py --version N
```

回滚只删除版本簿记，不会删除 `user_id`，也不会把 `*_isolation` 集合恢复到普通查询。回滚后应保持 `MULTI_ACCOUNT_ISOLATION_ENFORCE=true`，直到确认新版本不再需要旧数据入口。

# zhitouagent 腾讯云部署指南

## 架构概览

```
开发者 git push → Gitee → Webhook(:9000) → deploy.sh → docker compose up
                                                ↓
                              Nginx(:80) → Frontend + Backend(:8000)
                                              ↓           ↓
                                          MongoDB      Redis
                                         (127.0.0.1)  (127.0.0.1)
```

## 前置要求

- 腾讯云 CVM（x86_64），推荐 2C4G 以上
- Docker + Docker Compose V2 已安装
- Gitee 私有仓库访问权限
- 至少一个 AI 模型 API Key（推荐 DeepSeek）

## 一、首次部署

### 1. SSH 登录服务器

```bash
ssh root@your-server-ip
```

### 2. 上传代码到服务器

将本项目代码传到服务器（方式任选其一）：

```bash
# 方式A: 本地 scp 上传（最简单，无需认证）
scp -r ./quanting-agent root@your-server-ip:/opt/zhitouagent/worktree/

# 方式B: 服务器上通过 SSH Key 克隆（推荐长期使用）
git clone <private-repository-url> /opt/zhitouagent/worktree

# 方式C: 服务器上通过私人令牌克隆
GIT_TOKEN=你的令牌 sudo -E bash -c 'git clone <private-repository-url> /opt/zhitouagent/worktree'
```

### 3. 运行初始化脚本

```bash
cd /opt/zhitouagent/worktree

# 如果使用 SSH Key（默认推荐）
sudo bash deploy/setup.sh <private-repository-url> feat/assistant

# 如果使用私人令牌（通过环境变量传入，不会写入文件）
GIT_TOKEN=你的令牌 sudo -E bash deploy/setup.sh <private-repository-url> feat/assistant
```

> ⚠️ **安全提示**：永远不要将私人令牌硬编码在脚本或代码中。使用环境变量 `GITEE_TOKEN` 传入，或使用 SSH Key 方式认证。

脚本会自动完成：
- ✅ 创建目录结构
- ✅ 配置 SSH Key（如需要会引导你操作）
- ✅ 生成随机密钥的 `.env` 文件
- ✅ 启动所有 Docker 服务
- ✅ 注册 Webhook 系统服务

### 4. 配置 AI 模型密钥

```bash
vim /opt/zhitouagent/worktree/.env

# 至少填写以下一项:
DEEPSEEK_API_KEY=sk-xxxxx
DEEPSEEK_ENABLED=true

# 或
DASHSCOPE_API_KEY=sk-xxxxx
DASHSCOPE_ENABLED=true
```

修改后重启后端：

```bash
cd /opt/zhitouagent/worktree
docker compose -f docker-compose.hub.nginx.yml restart backend
```

### 5. 开放安全组端口

在腾讯云控制台 → 安全组中开放：

| 端口 | 协议 | 来源 | 用途 |
|------|------|------|------|
| 80 | TCP | 0.0.0.0/0 | HTTP 访问 |
| 9000 | TCP | Gitee IP 段 | Webhook（可选） |

> ⚠️ **不要开放** 27017、6379、8000 端口到公网

### 6. 验证部署

```bash
# 检查容器状态
docker compose -f docker-compose.hub.nginx.yml ps

# 健康检查
curl http://localhost/health          # 应返回 "healthy"
curl http://localhost/api/health      # 应返回 JSON

# 查看日志
docker compose -f docker-compose.hub.nginx.yml logs -f backend
```

浏览器访问 `http://your-server-ip` 应看到前端页面。

---

## 二、CI/CD 配置（Gitee Webhook）

### 1. 确认 Webhook 服务已启动

```bash
systemctl status zhitouagent-webhook
# 应显示 active (running)
```

如果未启动：

```bash
systemctl start zhitouagent-webhook
systemctl enable zhitouagent-webhook
```

### 2. 获取 Webhook Secret

```bash
grep WEBHOOK_SECRET /opt/zhitouagent/worktree/.env
# 输出: WEBHOOK_SECRET=xxxxxxxxxx
```

### 3. 在 Gitee 配置 Webhook

1. 打开 mailto:zh75067197@gmail.com/settings#hooks
2. 点击「添加 WebHook」
3. 填写：
   - **URL**: `http://your-server-ip:9000/webhook`
   - **密码**: 上一步获取的 `WEBHOOK_SECRET` 值
   - **触发事件**: 勾选「Push」
4. 点击「添加」

### 4. 测试 Webhook

在 Gitee Webhook 页面点击「测试」，或在本地推送代码：

```bash
git push origin feat/assistant
```

观察服务器日志：

```bash
tail -f /opt/zhitouagent/logs/webhook.log
```

应看到类似输出：

```
📥 收到 Push: username → refs/heads/feat/assistant
🚀 触发部署: /opt/zhitouagent/worktree/deploy/deploy.sh feat/assistant
✅ 部署成功 (abc1234 by username)
```

---

## 三、日常运维

### 手动部署

```bash
bash /opt/zhitouagent/worktree/deploy/deploy.sh
```

### 查看服务状态

```bash
cd /opt/zhitouagent/worktree
docker compose -f docker-compose.hub.nginx.yml ps
```

### 查看日志

```bash
# 后端日志
docker compose -f docker-compose.hub.nginx.yml logs -f backend

# Webhook 日志
tail -f /opt/zhitouagent/logs/webhook.log

# 部署日志
tail -f /opt/zhitouagent/logs/deploy.log
```

### 重启单个服务

```bash
cd /opt/zhitouagent/worktree
docker compose -f docker-compose.hub.nginx.yml restart backend   # 重启后端
docker compose -f docker-compose.hub.nginx.yml restart frontend  # 重启前端
```

### 更新代码但不自动部署

```bash
cd /opt/zhitouagent/worktree
git pull origin feat/assistant
# 然后手动执行部署
bash deploy/deploy.sh
```

### 停止所有服务

```bash
cd /opt/zhitouagent/worktree
docker compose -f docker-compose.hub.nginx.yml down
```

### 备份数据

```bash
# 备份 MongoDB
docker exec zhitouagent-mongodb mongodump --out /tmp/mongodump \
  -u admin -p "$(grep MONGODB_PASSWORD /opt/zhitouagent/worktree/.env | cut -d= -f2)" \
  --authenticationDatabase admin

# 备份 .env
cp /opt/zhitouagent/worktree/.env /opt/zhitouagent/.env.backup.$(date +%Y%m%d)
```

---

## 四、故障排查

| 问题 | 排查方法 |
|------|----------|
| 前端无法访问 | `docker compose ps` 检查 nginx/frontend 状态 |
| API 返回 502 | `docker compose logs backend` 查看后端错误 |
| 数据库连接失败 | 检查 `.env` 中 MongoDB 密码是否与容器环境变量一致 |
| Webhook 不触发 | `systemctl status zhitouagent-webhook` + 检查安全组 9000 端口 |
| 镜像拉取慢 | 配置 Docker 国内镜像加速器 |
| 内存不足 | `docker stats` 查看各容器内存使用 |

### Docker 镜像加速（推荐）

```bash
cat > /etc/docker/daemon.json << EOF
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://hub-mirror.c.163.com"
  ]
}
EOF
systemctl restart docker
```

---

## 五、HTTPS 配置（可选）

### 使用 Let's Encrypt 免费证书

```bash
# 安装 certbot
apt install -y certbot

# 申请证书（先停 80 端口或用 webroot 模式）
certbot certonly --standalone -d your-domain.com

# 复制证书
mkdir -p /opt/zhitouagent/worktree/nginx/certs
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/zhitouagent/worktree/nginx/certs/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/zhitouagent/worktree/nginx/certs/
```

修改 `deploy/docker-compose.prod.override.yml` 取消 443 端口注释，并更新 Nginx 配置添加 SSL。

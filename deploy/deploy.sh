#!/bin/bash
# TradingAgents-CN 部署核心脚本
# 被 setup.sh、post-receive hook、webhook-server 调用
# 用法: ./deploy.sh [branch]

set -euo pipefail

DEPLOY_DIR="/opt/tradingagents/worktree"
LOCAL_COMPOSE="deploy/docker-compose.local-build.yml"
HUB_COMPOSE="docker-compose.hub.nginx.yml"
BRANCH="${1:-feat/assistant}"
LOG_FILE="/opt/tradingagents/logs/deploy.log"
LOCK_FILE="/tmp/tradingagents-deploy.lock"

# 自动选择 compose 文件：优先本地构建版
if [ -f "$DEPLOY_DIR/$LOCAL_COMPOSE" ]; then
    COMPOSE_FILE="$LOCAL_COMPOSE"
else
    COMPOSE_FILE="$HUB_COMPOSE"
fi

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# 防止并发部署
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE")
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        log "⚠️  另一个部署进程正在运行 (PID: $LOCK_PID)，跳过本次部署"
        exit 0
    else
        rm -f "$LOCK_FILE"
    fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

mkdir -p "$(dirname "$LOG_FILE")"

log "🚀 开始部署 TradingAgents-CN (分支: $BRANCH)"

# 1. 拉取最新代码
log "📥 拉取最新代码..."
cd "$DEPLOY_DIR"

# 如果 remote 是 HTTPS 且设置了 GITEE_TOKEN，确保认证可用
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$REMOTE_URL" == https://* ]] && [ -n "${GITEE_TOKEN:-}" ]; then
    # 使用 credential helper 避免明文写在 URL 中
    git config credential.helper store
    echo "https://oauth2:${GITEE_TOKEN}@gitee.com" > ~/.git-credentials
    chmod 600 ~/.git-credentials
fi

git fetch origin "$BRANCH"
git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"
COMMIT=$(git rev-parse --short HEAD)
log "📌 当前提交: $COMMIT"

# 2. 确保 .env 存在
if [ ! -f ".env" ]; then
    log "❌ .env 文件不存在，请先运行 setup.sh"
    exit 1
fi

# 3. 构建/拉取 Docker 镜像
if [[ "$COMPOSE_FILE" == *"local-build"* ]]; then
    log "🔨 本地构建 Docker 镜像（仅重建变更部分）..."
    docker compose -f "$COMPOSE_FILE" build --no-cache=false
else
    log "🐳 拉取最新 Docker 镜像..."
    docker compose -f "$COMPOSE_FILE" pull mongodb redis backend frontend nginx
fi

# 4. 重启服务
log "🔄 重启服务..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# 5. 清理旧镜像
log "🧹 清理旧镜像..."
docker image prune -f 2>/dev/null || true

# 6. 等待健康检查
log "⏳ 等待服务就绪..."
sleep 10

HEALTHY=true
for i in $(seq 1 6); do
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        log "✅ Nginx 健康检查通过"
        break
    fi
    if [ "$i" -eq 6 ]; then
        log "⚠️  Nginx 健康检查超时，请手动检查"
        HEALTHY=false
    fi
    sleep 5
done

for i in $(seq 1 6); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        log "✅ Backend 健康检查通过"
        break
    fi
    if [ "$i" -eq 6 ]; then
        log "⚠️  Backend 健康检查超时，请手动检查"
        HEALTHY=false
    fi
    sleep 5
done

if [ "$HEALTHY" = true ]; then
    log "✅ 部署完成！提交: $COMMIT"
else
    log "⚠️  部署完成但部分服务未就绪，请检查日志: docker compose logs"
fi

# 输出当前容器状态
docker compose -f "$COMPOSE_FILE" ps 2>/dev/null | tee -a "$LOG_FILE"

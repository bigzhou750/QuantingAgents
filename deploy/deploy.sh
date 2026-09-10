#!/bin/bash
# zhitouagent 部署核心脚本
# 被 setup.sh、post-receive hook、webhook-server 调用
# 用法: ./deploy.sh [branch]

set -euo pipefail

DEPLOY_DIR="/opt/zhitouagent/worktree"
LOCAL_COMPOSE="deploy/docker-compose.local-build.yml"
HUB_COMPOSE="docker-compose.hub.nginx.yml"
BRANCH="${1:-feat/assistant}"
LOG_FILE="/opt/zhitouagent/logs/deploy.log"
LOCK_FILE="/tmp/zhitouagent-deploy.lock"

# 自动选择 compose 文件：优先本地构建版
if [ -f "$DEPLOY_DIR/$LOCAL_COMPOSE" ]; then
    COMPOSE_FILE="$LOCAL_COMPOSE"
    COMPOSE_CMD="docker compose -f $COMPOSE_FILE"
else
    COMPOSE_FILE="$HUB_COMPOSE"
    COMPOSE_CMD="docker compose -f $HUB_COMPOSE"
fi

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# 防止并发部署：如果已有部署在运行，先终止旧进程再开始新部署
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE")
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        log "⚠️  检测到旧部署进程 (PID: $LOCK_PID)，终止并重新开始..."
        kill "$LOCK_PID" 2>/dev/null || true
        # 等待旧进程退出
        for i in $(seq 1 10); do
            if ! kill -0 "$LOCK_PID" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        # 如果还没退出，强制杀死
        kill -9 "$LOCK_PID" 2>/dev/null || true
    fi
    rm -f "$LOCK_FILE"
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

mkdir -p "$(dirname "$LOG_FILE")"

log "🚀 开始部署 zhitouagent (分支: $BRANCH)"

# 1. 拉取最新代码
log "📥 拉取最新代码..."
cd "$DEPLOY_DIR"

# 如果 remote 是 HTTPS 且设置了 GITEE_TOKEN，确保认证可用
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$REMOTE_URL" == https://* ]] && [ -n "${GITEE_TOKEN:-}" ]; then
    git config credential.helper store
    echo "https://oauth2:${GITEE_TOKEN}@gitee.com" > ~/.git-credentials
    chmod 600 ~/.git-credentials
fi

git fetch origin "$BRANCH"
git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"
COMMIT=$(git rev-parse --short HEAD)
log "📌 当前提交: $COMMIT"

# 2. 确保 .env 存在并同步到 deploy 目录
if [ ! -f ".env" ]; then
    log "❌ .env 文件不存在，请先运行 setup.sh"
    exit 1
fi
cp .env deploy/.env
log "📋 .env 已同步到 deploy/"

# 3. 智能构建 Docker 镜像（利用 Docker 层缓存加速）
if [[ "$COMPOSE_FILE" == *"local-build"* ]]; then
    # 检测哪些服务需要重建
    SERVICES_TO_BUILD=""

    # 检查后端是否有变更（app/ tradingagents/ pyproject.toml 等）
    BACKEND_CHANGED=false
    if git diff HEAD~1 --name-only 2>/dev/null | grep -qE '^(app/|tradingagents/|cli/|vibe_agent_runtime/|config/|pyproject\.toml|Dockerfile\.backend)'; then
        BACKEND_CHANGED=true
    fi

    # 检查前端是否有变更（frontend/ 目录）
    FRONTEND_CHANGED=false
    if git diff HEAD~1 --name-only 2>/dev/null | grep -qE '^frontend/'; then
        FRONTEND_CHANGED=true
    fi

    # 如果是首次部署或无法判断变更，全部重建
    if [ -z "$(docker images -q zhitouagent-backend:local 2>/dev/null)" ]; then
        log "🔨 首次部署，构建所有服务..."
        SERVICES_TO_BUILD="backend frontend"
    elif [ -z "$(docker images -q zhitouagent-frontend:local 2>/dev/null)" ]; then
        log "🔨 前端镜像缺失，构建所有服务..."
        SERVICES_TO_BUILD="backend frontend"
    else
        # 根据变更情况决定构建范围
        if [ "$BACKEND_CHANGED" = true ] && [ "$FRONTEND_CHANGED" = true ]; then
            SERVICES_TO_BUILD="backend frontend"
            log "🔨 前后端均有变更，构建 backend + frontend..."
        elif [ "$BACKEND_CHANGED" = true ]; then
            SERVICES_TO_BUILD="backend"
            log "🔨 仅后端有变更，构建 backend（前端使用缓存）..."
        elif [ "$FRONTEND_CHANGED" = true ]; then
            SERVICES_TO_BUILD="frontend"
            log "🔨 仅前端有变更，构建 frontend（后端使用缓存）..."
        else
            # 没有检测到代码变更（可能是配置变更），仍重建以确保一致
            SERVICES_TO_BUILD="backend frontend"
            log "🔨 未检测到明确变更，全量构建以确保一致..."
        fi
    fi

    # 使用 Docker 层缓存构建（不加 --no-cache）
    # Docker 会自动检测 COPY 的文件是否变化，只重建受影响的层
    $COMPOSE_CMD build $SERVICES_TO_BUILD
else
    log "🐳 拉取最新 Docker 镜像..."
    $COMPOSE_CMD pull mongodb redis backend frontend nginx
fi

# 4. 重启服务（--force-recreate 确保使用新镜像）
log "🔄 重启服务..."
$COMPOSE_CMD up -d --force-recreate --remove-orphans

# 5. 清理旧镜像和构建缓存（防止磁盘占满）
log "🧹 清理旧镜像和构建缓存..."
docker image prune -f 2>/dev/null || true
# 清理超过 7 天的构建缓存，保留近期缓存加速后续构建
docker builder prune --filter "until=168h" -f 2>/dev/null || true

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
    log "⚠️  部署完成但部分服务未就绪，请检查日志: $COMPOSE_CMD logs"
fi

# 输出当前容器状态
$COMPOSE_CMD ps 2>/dev/null | tee -a "$LOG_FILE"

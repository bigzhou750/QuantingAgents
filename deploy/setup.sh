#!/bin/bash
# zhitouagent 腾讯云服务器首次部署初始化脚本
# 用法: sudo bash setup.sh [private-repository-url] [branch]
#
# 示例:
#   sudo bash setup.sh <private-repository-url> feat/assistant

set -euo pipefail

REPO_URL="${1:-}"
BRANCH="${2:-feat/assistant}"
DEPLOY_BASE="/opt/zhitouagent"
WORKTREE_DIR="$DEPLOY_BASE/worktree"
LOG_DIR="$DEPLOY_BASE/logs"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=============================================="
echo "  zhitouagent 首次部署初始化"
echo "=============================================="

if [ -z "$REPO_URL" ]; then
    echo "错误：必须提供私有仓库地址"
    exit 1
fi
echo "仓库地址: $REPO_URL"
echo "部署分支: $BRANCH"
echo "部署目录: $DEPLOY_BASE"
echo "=============================================="

# ==================== 1. 检查前置条件 ====================
echo ""
echo "📋 [1/7] 检查前置条件..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker:"
    echo "   curl -fsSL https://get.docker.com | sh"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose V2 未安装"
    exit 1
fi

echo "✅ Docker $(docker --version | awk '{print $3}' | tr -d ',')"
echo "✅ Docker Compose $(docker compose version --short)"

# ==================== 2. 创建目录结构 ====================
echo ""
echo "📁 [2/7] 创建目录结构..."

mkdir -p "$DEPLOY_BASE"/{logs,data,config}
mkdir -p "$WORKTREE_DIR"

# ==================== 3. 克隆代码 ====================
echo ""
echo "📥 [3/7] 克隆代码仓库..."

if [ -d "$WORKTREE_DIR/.git" ]; then
    echo "✅ Git 仓库已存在"
    cd "$WORKTREE_DIR"

    # 如果提供了 GIT_TOKEN，切换到 HTTPS 认证
    if [ -n "${GIT_TOKEN:-}" ]; then
        HTTPS_URL="$REPO_URL"
        git remote set-url origin "$HTTPS_URL"
        echo "🔑 已配置 HTTPS + Token 认证"
    fi

    echo "📥 拉取最新代码..."
    if ! git fetch origin 2>/dev/null; then
        echo "⚠️  git fetch 失败，可能是 SSH Key 未配置"
        echo ""
        echo "请选择操作:"
        echo "  1) 使用私人令牌认证（推荐）"
        echo "  2) 手动配置 SSH Key 后重试"
        echo "  3) 跳过代码更新，继续部署"
        read -rp "请选择 [1/2/3]: " FETCH_CHOICE
        case "$FETCH_CHOICE" in
            1)
                if [ -z "${GIT_TOKEN:-}" ]; then
                    read -rsp "请输入代码仓库私人令牌: " GIT_TOKEN
                    echo ""
                fi
                HTTPS_URL="$REPO_URL"
                git remote set-url origin "$HTTPS_URL"
                git fetch origin
                ;;
            2)
                echo "请配置 SSH Key 后重新运行此脚本"
                exit 1
                ;;
            3)
                echo "⏭️  跳过代码更新"
                ;;
        esac
    fi
elif [ -d "$WORKTREE_DIR" ] && [ "$(ls -A "$WORKTREE_DIR" 2>/dev/null)" ]; then
    # 目录存在且非空，但不是 git 仓库
    echo ""
    echo "⚠️  目录 $WORKTREE_DIR 已存在但不是 Git 仓库"
    echo ""
    echo "请选择操作:"
    echo "  1) 删除并重新克隆（推荐）"
    echo "  2) 在现有目录中初始化 Git 并关联远程仓库"
    echo "  3) 取消退出"
    read -rp "请选择 [1/2/3]: " DIR_CHOICE

    case "$DIR_CHOICE" in
        1)
            echo "🗑️  备份到 ${WORKTREE_DIR}.bak.$(date +%Y%m%d%H%M%S)..."
            mv "$WORKTREE_DIR" "${WORKTREE_DIR}.bak.$(date +%Y%m%d%H%M%S)"
            mkdir -p "$WORKTREE_DIR"
            ;;
        2)
            cd "$WORKTREE_DIR"
            git init
            git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
            git fetch origin
            git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
            echo "✅ 已关联远程仓库"
            # 跳过下面的克隆逻辑
            SKIP_CLONE=true
            ;;
        3)
            echo "❌ 已取消"
            exit 1
            ;;
    esac
fi

if [ "${SKIP_CLONE:-false}" != "true" ] && [ ! -d "$WORKTREE_DIR/.git" ]; then
    # 对于私有仓库，尝试 SSH 方式克隆
    SSH_REPO_URL=$(echo "$REPO_URL" | sed 's|https://gitee.com/|git@gitee.com:|')

    # 检查是否有 SSH Key
    if [ ! -f ~/.ssh/id_rsa ] && [ ! -f ~/.ssh/id_ed25519 ]; then
        echo ""
        echo "⚠️  未检测到 SSH Key，Gitee 私有仓库需要 SSH 认证"
        echo ""
        echo "请选择操作:"
        echo "  1) 生成新的 SSH Key（推荐）"
        echo "  2) 我已有 SSH Key，手动配置后重试"
        echo "  3) 使用 HTTPS + Token 方式克隆"
        read -rp "请选择 [1/2/3]: " CHOICE

        case "$CHOICE" in
            1)
                ssh-keygen -t ed25519 -C "zhitouagent-deploy" -f ~/.ssh/id_ed25519 -N ""
                echo ""
                echo "📋 请将以下公钥添加到 Gitee → 设置 → SSH公钥:"
                echo "---"
                cat ~/.ssh/id_ed25519.pub
                echo "---"
                echo ""
                read -rp "添加完成后按回车继续..."
                ;;
            2)
                echo "请配置好 SSH Key 后重新运行此脚本"
                exit 1
                ;;
            3)
                # 优先从环境变量读取，避免令牌出现在命令历史中
                if [ -n "${GIT_TOKEN:-}" ]; then
                    echo "✅ 已从环境变量 GIT_TOKEN 获取令牌"
                else
                    read -rsp "请输入代码仓库私人令牌 (不会显示在屏幕上): " GIT_TOKEN
                    echo ""
                fi
                if [ -z "$GIT_TOKEN" ]; then
                    echo "❌ 未提供令牌，退出"
                    exit 1
                fi
                SSH_REPO_URL="$REPO_URL"
                ;;
        esac
    fi

    # 尝试 SSH 克隆，失败则用 HTTPS
    if git clone "$SSH_REPO_URL" "$WORKTREE_DIR" 2>/dev/null; then
        echo "✅ 通过 SSH 克隆成功"
    elif git clone "$REPO_URL" "$WORKTREE_DIR"; then
        echo "✅ 通过 HTTPS 克隆成功"
    else
        echo "❌ 克隆失败，请检查网络或认证配置"
        exit 1
    fi
fi

cd "$WORKTREE_DIR"
git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
echo "✅ 代码就绪: $(git rev-parse --short HEAD)"

# ==================== 4. 生成生产环境 .env ====================
echo ""
echo "🔐 [4/7] 生成生产环境配置..."

if [ -f "$WORKTREE_DIR/.env" ]; then
    echo "⚠️  .env 已存在，跳过生成（如需重新生成请删除 .env）"
else
    TEMPLATE="$WORKTREE_DIR/deploy/env.production.template"

    if [ ! -f "$TEMPLATE" ]; then
        echo "❌ 模板文件不存在: $TEMPLATE"
        echo "   请确保 deploy/env.production.template 在仓库中"
        exit 1
    fi

    # 生成随机安全密钥（数据库密码使用默认值，与 compose 文件保持一致）
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null || openssl rand -base64 48)
    CSRF_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null || openssl rand -base64 48)
    WEBHOOK_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)

    # 复制模板并替换安全密钥占位符
    cp "$TEMPLATE" "$WORKTREE_DIR/.env"
    sed -i \
        -e "s|{{JWT_SECRET}}|${JWT_SECRET}|g" \
        -e "s|{{CSRF_SECRET}}|${CSRF_SECRET}|g" \
        -e "s|{{WEBHOOK_SECRET}}|${WEBHOOK_SECRET}|g" \
        "$WORKTREE_DIR/.env"

    chmod 600 "$WORKTREE_DIR/.env"

    echo "✅ .env 已生成（JWT/CSRF/Webhook 密钥已随机化）"
    echo ""
    echo "⚠️  重要：请编辑 .env 填入 AI 模型 API 密钥:"
    echo "   vim $WORKTREE_DIR/.env"
    echo "   至少配置 DEEPSEEK_API_KEY 或 DASHSCOPE_API_KEY"
    echo ""
fi

# 同步 .env 到 deploy/ 目录（compose 文件从该目录读取）
cp "$WORKTREE_DIR/.env" "$WORKTREE_DIR/deploy/.env"
echo "📋 .env 已同步到 deploy/"

# ==================== 5. 设置 Git 远程仓库为 SSH ====================
echo ""
echo "🔗 [5/7] 配置 Git 远程仓库..."

cd "$WORKTREE_DIR"
CURRENT_REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
SSH_REMOTE=$(echo "$REPO_URL" | sed 's|https://gitee.com/|git@gitee.com:|')

if [[ "$CURRENT_REMOTE" == https://* ]]; then
    git remote set-url origin "$SSH_REMOTE" 2>/dev/null || true
    echo "✅ 远程仓库已切换为 SSH: $SSH_REMOTE"
else
    echo "✅ 远程仓库: $(git remote get-url origin)"
fi

# ==================== 6. 安装 Webhook 服务 ====================
echo ""
echo "🔔 [6/7] 配置 CI/CD Webhook 服务..."

WEBHOOK_SCRIPT="$WORKTREE_DIR/deploy/webhook-server.py"
WEBHOOK_SERVICE="/etc/systemd/system/zhitouagent-webhook.service"

if [ -f "$WEBHOOK_SCRIPT" ]; then
    # 获取 webhook secret
    WEBHOOK_SECRET_VAL=$(grep "^WEBHOOK_SECRET=" "$WORKTREE_DIR/.env" | cut -d= -f2)

    # 创建 systemd service
    cat > "$WEBHOOK_SERVICE" << EOF
[Unit]
Description=zhitouagent Gitee Webhook Server
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=$WORKTREE_DIR
ExecStart=/usr/bin/python3 $WEBHOOK_SCRIPT --secret "$WEBHOOK_SECRET_VAL" --deploy-script "$WORKTREE_DIR/deploy/deploy.sh" --branch "$BRANCH"
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/webhook.log
StandardError=append:$LOG_DIR/webhook-error.log

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable zhitouagent-webhook
    systemctl start zhitouagent-webhook
    echo "✅ Webhook 服务已启动 (端口 9000)"
else
    echo "⚠️  webhook-server.py 不存在，跳过 CI/CD 配置"
fi

# ==================== 7. 首次启动服务 ====================
echo ""
echo "🚀 [7/7] 首次启动所有服务..."

cd "$WORKTREE_DIR"

# 优先使用本地构建版（Docker Hub 镜像可能不可用）
LOCAL_COMPOSE="deploy/docker-compose.local-build.yml"
HUB_COMPOSE="docker-compose.hub.nginx.yml"

if [ -f "$LOCAL_COMPOSE" ]; then
    COMPOSE_FILE="$LOCAL_COMPOSE"
    echo "📦 使用本地构建模式 (首次构建约10-20分钟，请耐心等待)"
    docker compose -f "$COMPOSE_FILE" up -d --build
elif [ -f "$HUB_COMPOSE" ]; then
    COMPOSE_FILE="$HUB_COMPOSE"
    echo "📦 使用 Docker Hub 镜像模式"
    docker compose -f "$COMPOSE_FILE" up -d
else
    echo "❌ 未找到 docker-compose 配置文件"
    exit 1
fi

echo ""
echo "=============================================="
echo "  ✅ 部署初始化完成！"
echo "=============================================="
echo ""
echo "📊 查看服务状态:"
echo "   cd $WORKTREE_DIR && docker compose -f $COMPOSE_FILE ps"
echo ""
echo "📝 查看日志:"
echo "   docker compose -f $COMPOSE_FILE logs -f backend"
echo ""
echo "🌐 访问地址:"
echo "   http://$(hostname -I | awk '{print $1}')"
echo ""
echo "🔧 后续步骤:"
echo "   1. 编辑 .env 填入 AI 模型 API 密钥"
echo "      vim $WORKTREE_DIR/.env"
echo "   2. 重启后端使配置生效"
echo "      cd $WORKTREE_DIR && docker compose -f $COMPOSE_FILE restart backend"
echo "   3. 配置 Gitee Webhook（见 deploy/README.md）"
echo "   4. 腾讯云安全组开放 80 端口"
echo ""
echo "🔄 CI/CD 说明:"
echo "   Push 到 Gitee '$BRANCH' 分支后，Webhook 自动触发部署"
echo "   手动部署: bash $WORKTREE_DIR/deploy/deploy.sh"
echo "=============================================="

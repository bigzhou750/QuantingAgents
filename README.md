# zhitouagent 智能投研助手

zhitouagent 是一套面向 A 股、港股和美股研究场景的多智能体投研平台。系统提供股票分析、批量研究、选股、投资画像、新闻关注、模拟交易和 Agent 研究能力，AI 分析结果仅用于学习研究参考，不构成投资建议。

## 技术架构

- Backend: Python 3.10+, FastAPI, MongoDB, Redis
- Frontend: Vue 3, TypeScript, Vite, Element Plus
- Runtime: Agent 运行时兼容层保留内部能力，外部产品标识统一为 zhitouagent
- AI Model: 默认使用 DeepSeek，模型配置由后端环境配置统一管理

## 快速启动

本地开发请使用项目既有的启动脚本。生产部署请参考 `deploy/README.md`，不要直接使用仓库内示例密码或本地 `.env`。

```bash
# 后端
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端
cd frontend
yarn install
yarn dev
```

## 配置说明

### 模型配置

生产环境只使用 DeepSeek 作为默认运行模型：

```bash
DEEPSEEK_API_KEY=<真实密钥>
DEEPSEEK_ENABLED=true
```

普通用户不配置模型供应商或 API Key。模型、密钥和默认参数由后端配置决定，管理员可通过配置管理维护。

### 安全配置

上线前必须显式配置：

```bash
MONGODB_PASSWORD=<随机强密码>
REDIS_PASSWORD=<随机强密码>
JWT_SECRET=<随机密钥>
CSRF_SECRET=<随机密钥>
ALLOWED_ORIGINS=<正式域名>
ALLOWED_HOSTS=<正式域名>
```

禁止将 `.env`、真实 API Key、数据库密码、JWT/CSRF 密钥提交到 Git 或发布包。本地或历史构建中出现过的 DeepSeek Key 必须在上线前轮换。

### 管理员初始化

系统不再使用公开默认账号。首次启动需通过受控方式提供管理员初始密码：

```bash
INITIAL_ADMIN_PASSWORD=<强密码> python scripts/create_default_admin.py
```

后端启动日志不会输出明文密码。

## 发布与验收

正式发布前执行：

```bash
python scripts/validation/build_release_tree.py . /tmp/zhitouagent-release
python scripts/validation/release_scan.py /tmp/zhitouagent-release
```

发布扫描必须通过。扫描器会排除历史基线文件、许可证/归属文件和内部兼容包路径，但不会放宽真实密钥、旧公开邮箱、旧项目仓库链接或旧产品品牌残留。

## 许可与归属

本项目使用混合许可模式，具体权利与归属请阅读 `COPYRIGHT.md` 和 `LICENSE`。第三方依赖的许可证和归属信息保留在对应 NOTICE 与许可证文件中。

## 支持

产品问题请联系 `zh75067197@gmail.com`。

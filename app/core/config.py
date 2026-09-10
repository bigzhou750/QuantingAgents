from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os
import warnings
import re
import getpass
from pathlib import Path

# Legacy env var aliases (deprecated): map API_HOST/PORT/DEBUG -> HOST/PORT/DEBUG
_LEGACY_ENV_ALIASES = {
    "API_HOST": "HOST",
    "API_PORT": "PORT",
    "API_DEBUG": "DEBUG",
}
for _legacy, _new in _LEGACY_ENV_ALIASES.items():
    if _new not in os.environ and _legacy in os.environ:
        os.environ[_new] = os.environ[_legacy]
        warnings.warn(
            f"Environment variable {_legacy} is deprecated; use {_new} instead.",
            DeprecationWarning,
            stacklevel=2,
        )

class Settings(BaseSettings):
    # 基础配置
    DEBUG: bool = Field(default=True)
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])
    ALLOWED_HOSTS: List[str] = Field(default_factory=lambda: ["*"])

    # MongoDB配置
    MONGODB_HOST: str = Field(default="localhost")
    MONGODB_PORT: int = Field(default=27017)
    MONGODB_USERNAME: str = Field(default="")
    MONGODB_PASSWORD: str = Field(default="")
    MONGODB_DATABASE: str = Field(default="tradingagentscn")
    MONGODB_DATABASE_SCOPE: str = Field(default="auto")
    MONGODB_DATABASE_INSTANCE: str = Field(default="")
    ALLOW_SHARED_DB_IN_DEBUG: bool = Field(default=False)
    MONGODB_AUTH_SOURCE: str = Field(default="admin")
    MONGO_MAX_CONNECTIONS: int = Field(default=100)
    MONGO_MIN_CONNECTIONS: int = Field(default=10)
    # MongoDB超时参数（毫秒）- 用于处理大量历史数据
    MONGO_CONNECT_TIMEOUT_MS: int = Field(default=30000)  # 连接超时：30秒（原为10秒）
    MONGO_SOCKET_TIMEOUT_MS: int = Field(default=60000)   # 套接字超时：60秒（原为20秒）
    MONGO_SERVER_SELECTION_TIMEOUT_MS: int = Field(default=5000)  # 服务器选择超时：5秒

    @property
    def MONGO_URI(self) -> str:
        """构建MongoDB URI"""
        if self.MONGODB_USERNAME and self.MONGODB_PASSWORD:
            return f"mongodb://{self.MONGODB_USERNAME}:{self.MONGODB_PASSWORD}@{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGO_DB}?authSource={self.MONGODB_AUTH_SOURCE}"
        else:
            return f"mongodb://{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGO_DB}"

    @property
    def MONGO_DB(self) -> str:
        """获取数据库名称"""
        scope = (self.MONGODB_DATABASE_SCOPE or "").strip().lower()
        if not scope or scope == "auto":
            scope = "major_instance" if self.DEBUG else "explicit"

        if scope == "explicit":
            return self.MONGODB_DATABASE

        base = self.MONGODB_DATABASE
        major = _read_major_version()

        if scope == "major":
            name = f"{base}_v{major}"
            return _sanitize_mongo_db_name(name)

        if scope == "major_instance":
            instance = (self.MONGODB_DATABASE_INSTANCE or "").strip()
            if not instance:
                instance = _default_instance_tag()
            name = f"{base}_v{major}_{instance}"
            return _sanitize_mongo_db_name(name)

        return _sanitize_mongo_db_name(base)

    @property
    def MONGO_DB_IDENTITY(self) -> dict:
        scope = (self.MONGODB_DATABASE_SCOPE or "").strip().lower() or "auto"
        if scope == "auto":
            resolved_scope = "major_instance" if self.DEBUG else "explicit"
        else:
            resolved_scope = scope

        major = _read_major_version()
        instance = (self.MONGODB_DATABASE_INSTANCE or "").strip()
        if resolved_scope == "major_instance" and not instance:
            instance = _default_instance_tag()

        return {
            "base_database": self.MONGODB_DATABASE,
            "scope_configured": scope,
            "scope_effective": resolved_scope,
            "major_version": major,
            "instance": instance,
            "database": self.MONGO_DB,
        }

    # Redis配置
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_PASSWORD: str = Field(default="")
    REDIS_DB: int = Field(default=0)
    REDIS_MAX_CONNECTIONS: int = Field(default=20)
    REDIS_RETRY_ON_TIMEOUT: bool = Field(default=True)

    @property
    def REDIS_URL(self) -> str:
        """构建Redis URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        else:
            return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # JWT配置
    JWT_SECRET: str = Field(default="change-me-in-production")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)
    AUTH_REGISTRATION_ENABLED: bool = Field(default=True)
    AUTH_PASSWORD_MIN_LENGTH: int = Field(default=8, ge=6, le=128)
    AUTH_LOGIN_RATE_LIMIT: int = Field(default=10, ge=1, le=1000)
    AUTH_REGISTER_RATE_LIMIT: int = Field(default=5, ge=1, le=1000)
    AUTH_TOKEN_REVOCATION_ENABLED: bool = Field(default=True)
    AUTH_TOKEN_ISSUER: str = Field(default="quantingagents")

    # 队列配置
    QUEUE_MAX_SIZE: int = Field(default=10000)
    QUEUE_VISIBILITY_TIMEOUT: int = Field(default=300)  # 5分钟
    QUEUE_MAX_RETRIES: int = Field(default=3)
    WORKER_HEARTBEAT_INTERVAL: int = Field(default=30)  # 30秒


    # 队列轮询/清理间隔（秒）
    QUEUE_POLL_INTERVAL_SECONDS: float = Field(default=1.0)
    QUEUE_CLEANUP_INTERVAL_SECONDS: float = Field(default=60.0)

    # 并发控制
    DEFAULT_USER_CONCURRENT_LIMIT: int = Field(default=3)
    GLOBAL_CONCURRENT_LIMIT: int = Field(default=50)
    DEFAULT_DAILY_QUOTA: int = Field(default=1000)

    # 速率限制
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    DEFAULT_RATE_LIMIT: int = Field(default=100)  # 每分钟请求数

    # 日志配置
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    LOG_FILE: str = Field(default="logs/tradingagents.log")

    # 代理配置
    # 用于配置需要绕过代理的域名（国内数据源）
    # 多个域名用逗号分隔
    # ⚠️ Windows 不支持通配符 *，必须使用完整域名
    # 详细说明: docs/proxy_configuration.md
    HTTP_PROXY: str = Field(default="")
    HTTPS_PROXY: str = Field(default="")
    NO_PROXY: str = Field(
        default="localhost,127.0.0.1,eastmoney.com,push2.eastmoney.com,82.push2.eastmoney.com,82.push2delay.eastmoney.com,gtimg.cn,sinaimg.cn,api.tushare.pro,baostock.com"
    )

    # 文件上传配置
    MAX_UPLOAD_SIZE: int = Field(default=10 * 1024 * 1024)  # 10MB
    UPLOAD_DIR: str = Field(default="uploads")

    # 缓存配置
    CACHE_TTL: int = Field(default=3600)  # 1小时
    SCREENING_CACHE_TTL: int = Field(default=1800)  # 30分钟

    # 安全配置
    BCRYPT_ROUNDS: int = Field(default=12)
    SESSION_EXPIRE_HOURS: int = Field(default=24)
    CSRF_SECRET: str = Field(default="change-me-csrf-secret")

    # 外部服务配置
    STOCK_DATA_API_URL: str = Field(default="")
    STOCK_DATA_API_KEY: str = Field(default="")

    # SSE 配置
    SSE_POLL_TIMEOUT_SECONDS: float = Field(default=1.0)
    SSE_HEARTBEAT_INTERVAL_SECONDS: int = Field(default=10)
    SSE_TASK_MAX_IDLE_SECONDS: int = Field(default=300)
    SSE_BATCH_POLL_INTERVAL_SECONDS: float = Field(default=2.0)
    SSE_BATCH_MAX_IDLE_SECONDS: int = Field(default=600)

    # Embedded Vibe Agent runtime. This is data, never source code.
    VIBE_AGENT_RUNTIME_ROOT: str = Field(default="~/.quantingagents/runtime/vibe-agent")
    USER_RUNTIME_ROOT: str = Field(default="~/.quantingagents/runtime/users")
    MULTI_ACCOUNT_ISOLATION_ENABLED: bool = Field(default=True)
    MULTI_ACCOUNT_ISOLATION_ENFORCE: bool = Field(default=False)
    MULTI_ACCOUNT_MIGRATION_VERSION: int = Field(default=0, ge=0)
    VIBE_AGENT_WORKER_ENABLED: bool = Field(default=True)
    VIBE_AGENT_WORKER_ID: str = Field(default="quanting-vibe-worker")
    VIBE_AGENT_WORKER_CONCURRENCY: int = Field(default=2, ge=1, le=8)
    VIBE_AGENT_TASK_TIMEOUT_SECONDS: int = Field(default=900, ge=30, le=7200)

    # ==================== Agent 评测平台配置 ====================
    EVAL_PLATFORM_ENABLED: bool = Field(default=False, description="是否启用 Agent 评测平台（默认关闭）")
    EVAL_RUNNER_CONCURRENCY: int = Field(default=2, ge=1, le=8, description="评测运行并发数")
    EVAL_TRIAL_TIMEOUT_SECONDS: int = Field(default=600, ge=60, le=3600, description="单个 trial 超时时间（秒）")
    EVAL_MAX_TRIALS_PER_CASE: int = Field(default=10, ge=1, le=50, description="每个 case 最大 trial 次数")
    EVAL_JUDGE_MODEL: str = Field(default="", description="LLM-as-judge 使用的模型（留空使用默认模型）")
    EVAL_OBSERVABILITY_BACKEND: str = Field(default="none", description="评测观测后端: none/langfuse/phoenix")
    EVAL_OBSERVABILITY_API_KEY: str = Field(default="", description="评测观测后端 API key")
    EVAL_OBSERVABILITY_HOST: str = Field(default="", description="评测观测后端地址")
    EVAL_OBSERVABILITY_PROJECT: str = Field(default="quantingagents-eval", description="评测观测项目名")
    ONLINE_BADCASE_ENABLED: bool = Field(default=False, description="是否启用线上 Bad Case 自动发现")
    ONLINE_BADCASE_ENABLE_JUDGE: bool = Field(default=False, description="是否对线上输出启用 LLM Judge 软信号")
    ONLINE_BADCASE_SOFT_SAMPLE_RATE: float = Field(default=0.1, ge=0.0, le=1.0, description="软质量信号采样率")
    ONLINE_BADCASE_CONFIDENCE_THRESHOLD: float = Field(default=0.8, ge=0.0, le=1.0, description="自动确认置信度阈值")
    ONLINE_BADCASE_JUDGE_THRESHOLD: float = Field(default=0.6, ge=0.0, le=1.0, description="LLM Judge 低分阈值")
    ONLINE_BADCASE_EVIDENCE_THRESHOLD: float = Field(default=0.6, ge=0.0, le=1.0, description="证据评分低分阈值")
    ONLINE_BADCASE_MAX_CONTENT_LENGTH: int = Field(default=5000, ge=1000, le=200000, description="Bad Case 最大内容长度")
    ONLINE_BADCASE_DATASET_PURPOSES: str = Field(
        default="online_regression,review_queue,detector_eval,golden",
        description="评测集分层用途（逗号分隔）",
    )

    # ==================== Agent 决策可解释与审计配置 ====================
    EXPLAINABILITY_ENABLED: bool = Field(
        default=True,
        description="是否启用 Agent 决策链、解释校验与审计能力",
    )
    DECISION_AUDIT_ENABLED: bool = Field(
        default=True,
        description="是否启用按业务 ID 的统一决策审计查询",
    )
    EXPLAINABILITY_MODE: str = Field(
        default="strict",
        description="解释降级模式: strict/relaxed（strict 下高风险任务解释故障时暂停）",
    )
    EXPLAINABILITY_HIGH_RISK_THRESHOLD: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="高风险决策阈值",
    )
    EXPLAINABILITY_ALERT_THRESHOLD: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="解释不一致率或决策链完整率告警阈值",
    )

    # ==================== Agent 自进化配置 ====================
    EVOLUTION_ENABLED: bool = Field(default=False, description="是否启用 Agent 自进化闭环（默认关闭）")
    EVOLUTION_AUTOMATION_MODE: str = Field(default="manual", description="自动化模式: manual/semi-auto/auto")
    EVOLUTION_TRIGGER_REGRESSION_THRESHOLD: float = Field(default=0.05, ge=0.0, le=1.0, description="趋势回退触发阈值（成功率下降比例）")
    EVOLUTION_TRIGGER_BAD_CASE_COUNT: int = Field(default=10, ge=1, description="Bad Case 阈值触发数量")
    EVOLUTION_BUDGET_MAX_RUNS_PER_DAY: int = Field(default=5, ge=1, le=50, description="每日最大验证 run 次数")
    EVOLUTION_HUMAN_GATE: bool = Field(default=True, description="生产环境是否要求人工审批")
    EVOLUTION_ALLOWED_ARTIFACT_TYPES: str = Field(default="skill,prompt,rubric,policy,case", description="允许自进化的 artifact 类型（逗号分隔）")
    EVOLUTION_FORBIDDEN_TARGETS: str = Field(default="", description="禁止修改的 artifact ID 列表（逗号分隔）")
    EVOLUTION_SCHEDULE_CRON: str = Field(default="", description="定时触发表达式（空=禁用）")
    EVOLUTION_COOLDOWN_MINUTES: int = Field(default=60, ge=0, le=10080, description="相同失败模式冷却时间")
    EVOLUTION_CHANGE_BUDGET_CHARS: int = Field(default=20000, ge=100, le=200000, description="单提案最大变更字符数")
    EVOLUTION_DAILY_COST_BUDGET_USD: float = Field(default=10.0, ge=0, le=100000, description="每日验证成本预算")
    EVOLUTION_REQUIRE_SMOKE_TEST: bool = Field(default=True, description="发布后是否必须通过 smoke test")
    EVOLUTION_SKILL_REGRESSION_REQUIRED: bool = Field(
        default=True,
        description="Skill promote 前是否必须通过配对回归 gate",
    )
    EVOLUTION_SKILL_REGRESSION_OVERRIDE_ALLOWED: bool = Field(
        default=False,
        description="是否允许管理员显式覆盖 Skill 回归门禁",
    )
    EVOLUTION_ARTIFACT_RUNTIME_ROOT: str = Field(
        default="~/.quantingagents/runtime/evolution-artifacts",
        description="自进化 artifact 的正式 materialization 根目录",
    )
    EVOLUTION_FOLLOW_UP_WINDOW_MINUTES: int = Field(
        default=60,
        ge=5,
        le=10080,
        description="高风险发布反馈升级统计窗口",
    )
    EVOLUTION_OVERLAY_MAX_FILES: int = Field(
        default=32,
        ge=1,
        le=200,
        description="候选 overlay 最大可加载文件数",
    )

    # 监控配置
    METRICS_ENABLED: bool = Field(default=True)
    HEALTH_CHECK_INTERVAL: int = Field(default=60)  # 60秒


    # 配置真相来源（方案A）：file|db|hybrid
    # - file：以文件/env 为准（推荐，生产缺省）
    # - db：以数据库为准（仅兼容旧版，不推荐）
    # - hybrid：文件/env 优先，DB 作为兜底
    CONFIG_SOT: str = Field(default="file")


    # 基础信息同步任务配置（可配置调度）
    SYNC_STOCK_BASICS_ENABLED: bool = Field(default=True)
    # 优先使用 CRON 表达式，例如 "30 6 * * *" 表示每日 06:30
    SYNC_STOCK_BASICS_CRON: str = Field(default="")
    # 若未提供 CRON，则使用简单时间字符串 "HH:MM"（24小时制）
    SYNC_STOCK_BASICS_TIME: str = Field(default="06:30")
    # 时区
    TIMEZONE: str = Field(default="Asia/Shanghai")

    # 实时行情入库任务
    QUOTES_INGEST_ENABLED: bool = Field(default=True)
    QUOTES_INGEST_INTERVAL_SECONDS: int = Field(
        default=360,
        description="实时行情采集间隔（秒）。默认360秒（6分钟），免费用户建议>=300秒，付费用户可设置5-60秒"
    )
    # 休市期/启动兜底补数（填充上一笔快照）
    QUOTES_BACKFILL_ON_STARTUP: bool = Field(default=True)
    QUOTES_BACKFILL_ON_OFFHOURS: bool = Field(default=True)

    # 实时行情接口轮换配置
    QUOTES_ROTATION_ENABLED: bool = Field(
        default=True,
        description="启用接口轮换机制（Tushare → AKShare东方财富 → AKShare新浪财经）"
    )
    QUOTES_TUSHARE_HOURLY_LIMIT: int = Field(
        default=2,
        description="Tushare rt_k接口每小时调用次数限制（免费用户2次，付费用户可设置更高）"
    )
    QUOTES_AUTO_DETECT_TUSHARE_PERMISSION: bool = Field(
        default=True,
        description="自动检测Tushare rt_k接口权限，付费用户自动切换到高频模式（5秒）"
    )

    # Tushare基础配置
    TUSHARE_TOKEN: str = Field(default="", description="Tushare API Token")
    TUSHARE_ENABLED: bool = Field(default=True, description="启用Tushare数据源")
    TUSHARE_TIER: str = Field(default="standard", description="Tushare积分等级 (free/basic/standard/premium/vip)")
    TUSHARE_RATE_LIMIT_SAFETY_MARGIN: float = Field(default=0.8, ge=0.1, le=1.0, description="速率限制安全边际")

    # Tushare统一数据同步配置
    TUSHARE_UNIFIED_ENABLED: bool = Field(default=True)
    TUSHARE_BASIC_INFO_SYNC_ENABLED: bool = Field(default=True)
    TUSHARE_BASIC_INFO_SYNC_CRON: str = Field(default="0 2 * * *")  # 每日凌晨2点
    TUSHARE_QUOTES_SYNC_ENABLED: bool = Field(default=True)
    TUSHARE_QUOTES_SYNC_CRON: str = Field(default="*/5 9-15 * * 1-5")  # 交易时间每5分钟
    TUSHARE_HISTORICAL_SYNC_ENABLED: bool = Field(default=True)
    TUSHARE_HISTORICAL_SYNC_CRON: str = Field(default="0 16 * * 1-5")  # 工作日16点
    TUSHARE_FINANCIAL_SYNC_ENABLED: bool = Field(default=True)
    TUSHARE_FINANCIAL_SYNC_CRON: str = Field(default="0 3 * * 0")  # 周日凌晨3点
    TUSHARE_STATUS_CHECK_ENABLED: bool = Field(default=True)
    TUSHARE_STATUS_CHECK_CRON: str = Field(default="0 * * * *")  # 每小时

    # Tushare数据初始化配置
    TUSHARE_INIT_HISTORICAL_DAYS: int = Field(default=365, ge=1, le=3650, description="初始化历史数据天数")
    TUSHARE_INIT_BATCH_SIZE: int = Field(default=100, ge=10, le=1000, description="初始化批处理大小")
    TUSHARE_INIT_AUTO_START: bool = Field(default=False, description="应用启动时自动检查并初始化数据")

    # AKShare统一数据同步配置
    AKSHARE_UNIFIED_ENABLED: bool = Field(default=True, description="启用AKShare统一数据同步")
    AKSHARE_BASIC_INFO_SYNC_ENABLED: bool = Field(default=True, description="启用基础信息同步")
    AKSHARE_BASIC_INFO_SYNC_CRON: str = Field(default="0 3 * * *", description="基础信息同步CRON表达式")  # 每日凌晨3点
    AKSHARE_QUOTES_SYNC_ENABLED: bool = Field(default=True, description="启用行情同步")
    AKSHARE_QUOTES_SYNC_CRON: str = Field(default="*/30 9-15 * * 1-5", description="行情同步CRON表达式")  # 交易时间每30分钟（避免频率限制）
    AKSHARE_HISTORICAL_SYNC_ENABLED: bool = Field(default=True, description="启用历史数据同步")
    AKSHARE_HISTORICAL_SYNC_CRON: str = Field(default="0 17 * * 1-5", description="历史数据同步CRON表达式")  # 工作日17点
    AKSHARE_FINANCIAL_SYNC_ENABLED: bool = Field(default=True, description="启用财务数据同步")
    AKSHARE_FINANCIAL_SYNC_CRON: str = Field(default="0 4 * * 0", description="财务数据同步CRON表达式")  # 周日凌晨4点
    AKSHARE_STATUS_CHECK_ENABLED: bool = Field(default=True, description="启用状态检查")
    AKSHARE_STATUS_CHECK_CRON: str = Field(default="30 * * * *", description="状态检查CRON表达式")  # 每小时30分

    # AKShare数据初始化配置
    AKSHARE_INIT_HISTORICAL_DAYS: int = Field(default=365, ge=1, le=3650, description="初始化历史数据天数")
    AKSHARE_INIT_BATCH_SIZE: int = Field(default=100, ge=10, le=1000, description="初始化批处理大小")
    AKSHARE_INIT_AUTO_START: bool = Field(default=False, description="应用启动时自动检查并初始化数据")

    # ==================== 分析师数据获取配置 ====================

    # 市场分析师数据范围配置
    # 默认60天：可覆盖MA60等所有常用技术指标（MA5/10/20/60, MACD, RSI, BOLL）
    MARKET_ANALYST_LOOKBACK_DAYS: int = Field(default=60, ge=5, le=365, description="市场分析回溯天数（用于技术分析）")

    # ==================== BaoStock统一数据同步配置 ====================

    # BaoStock统一数据同步总开关
    BAOSTOCK_UNIFIED_ENABLED: bool = Field(default=True, description="启用BaoStock统一数据同步")

    # BaoStock数据同步任务配置
    BAOSTOCK_BASIC_INFO_SYNC_ENABLED: bool = Field(default=True, description="启用基础信息同步")
    BAOSTOCK_BASIC_INFO_SYNC_CRON: str = Field(default="0 4 * * *", description="基础信息同步CRON表达式")  # 每日凌晨4点
    BAOSTOCK_DAILY_QUOTES_SYNC_ENABLED: bool = Field(default=True, description="启用日K线同步（注意：BaoStock不支持实时行情）")
    BAOSTOCK_DAILY_QUOTES_SYNC_CRON: str = Field(default="0 16 * * 1-5", description="日K线同步CRON表达式")  # 工作日收盘后16:00
    BAOSTOCK_HISTORICAL_SYNC_ENABLED: bool = Field(default=True, description="启用历史数据同步")
    BAOSTOCK_HISTORICAL_SYNC_CRON: str = Field(default="0 18 * * 1-5", description="历史数据同步CRON表达式")  # 工作日18点
    BAOSTOCK_STATUS_CHECK_ENABLED: bool = Field(default=True, description="启用状态检查")
    BAOSTOCK_STATUS_CHECK_CRON: str = Field(default="45 * * * *", description="状态检查CRON表达式")  # 每小时45分

    # BaoStock数据初始化配置
    BAOSTOCK_INIT_HISTORICAL_DAYS: int = Field(default=365, ge=1, le=3650, description="初始化历史数据天数")
    BAOSTOCK_INIT_BATCH_SIZE: int = Field(default=50, ge=10, le=500, description="初始化批处理大小")
    BAOSTOCK_INIT_AUTO_START: bool = Field(default=False, description="应用启动时自动检查并初始化数据")

    # 数据目录配置
    ZHITOUAGENT_DATA_DIR: str = Field(default="./data")

    @property
    def TRADINGAGENTS_DATA_DIR(self) -> str:
        """Deprecated compatibility alias for legacy callers."""
        return self.ZHITOUAGENT_DATA_DIR

    @property
    def log_dir(self) -> str:
        """获取日志目录"""
        return os.path.dirname(self.LOG_FILE)

    # ==================== 港股数据配置 ====================

    # 港股数据源配置（按需获取+缓存模式）
    HK_DATA_CACHE_HOURS: int = Field(default=24, ge=1, le=168, description="港股数据缓存时长（小时）")
    HK_DEFAULT_DATA_SOURCE: str = Field(default="yfinance", description="港股默认数据源（yfinance/akshare）")

    # ==================== 美股数据配置 ====================

    # 美股数据源配置（按需获取+缓存模式）
    US_DATA_CACHE_HOURS: int = Field(default=24, ge=1, le=168, description="美股数据缓存时长（小时）")
    US_DEFAULT_DATA_SOURCE: str = Field(default="yfinance", description="美股默认数据源（yfinance/finnhub）")

    # ===== 新闻数据同步服务配置 =====
    NEWS_SYNC_ENABLED: bool = Field(default=True)
    NEWS_SYNC_CRON: str = Field(default="0 */2 * * *")  # 每2小时
    NEWS_SYNC_HOURS_BACK: int = Field(default=24)
    NEWS_SYNC_MAX_PER_SOURCE: int = Field(default=50)

    # ==================== 数据就绪检查配置 ====================
    DATA_READINESS_ENABLED: bool = Field(default=True, description="启用数据就绪检查")
    DATA_READINESS_REFRESH_CRON: str = Field(default="*/30 * * * *", description="数据就绪刷新调度")
    DATA_READINESS_FRESHNESS_STOCK_POOL_HOURS: int = Field(default=48, ge=1, description="股票池新鲜度阈值（小时）")
    DATA_READINESS_FRESHNESS_QUOTES_HOURS: int = Field(default=2, ge=1, description="行情新鲜度阈值（小时）")
    DATA_READINESS_FRESHNESS_HISTORICAL_HOURS: int = Field(default=26, ge=1, description="历史行情新鲜度阈值（小时）")
    DATA_READINESS_FRESHNESS_FINANCIAL_HOURS: int = Field(default=168, ge=1, description="财务数据新鲜度阈值（小时）")
    DATA_READINESS_FRESHNESS_INDEX_HOURS: int = Field(default=26, ge=1, description="指数数据新鲜度阈值（小时）")
    DATA_READINESS_MIN_COVERAGE_RATE: float = Field(default=0.5, ge=0.0, le=1.0, description="最低覆盖率阈值")

    # ==================== 策略模拟配置 ====================
    SIMULATION_ENABLED: bool = Field(default=True, description="启用策略模拟")
    SIMULATION_DEFAULT_LOOKBACK_DAYS: int = Field(default=365, ge=30, le=1825, description="默认回看天数")
    SIMULATION_MIN_COVERAGE_RATE: float = Field(default=0.5, ge=0.0, le=1.0, description="最低覆盖率以生成有效结果")
    SIMULATION_AUTO_RUN_CRON: str = Field(default="0 20 * * 1-5", description="收盘后自动模拟调度")

    @property
    def is_production(self) -> bool:
        """是否为生产环境"""
        return not self.DEBUG

    # Ignore any extra environment variables present in .env or process env
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()


def _read_major_version() -> str:
    v = os.getenv("ZHITOUAGENT_VERSION", "").strip() or os.getenv("APP_VERSION", "").strip()
    if not v:
        try:
            v = Path(__file__).resolve().parents[3].joinpath("VERSION").read_text(encoding="utf-8").strip()
        except Exception:
            v = ""

    m = re.match(r"^\s*(\d+)", v)
    return m.group(1) if m else "0"


def _default_instance_tag() -> str:
    user = os.getenv("ZHITOUAGENT_DB_USER", "").strip() or getpass.getuser()
    host = os.getenv("ZHITOUAGENT_DB_HOST", "").strip() or os.getenv("COMPUTERNAME", "").strip() or os.getenv("HOSTNAME", "").strip()
    tag = f"{user}-{host}" if host else user
    return _sanitize_mongo_db_name(tag).strip("_-").lower() or "local"


def _sanitize_mongo_db_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(name)).strip("._-")
    if not cleaned:
        return "tradingagentscn"

    max_len = 63
    if len(cleaned) <= max_len:
        return cleaned

    suffix = str(abs(hash(cleaned)) % (10**8)).rjust(8, "0")
    return f"{cleaned[:max_len-9]}_{suffix}"

# 自动将代理配置设置到环境变量
# 这样 requests 库可以直接读取 os.environ['NO_PROXY']
if settings.HTTP_PROXY:
    os.environ['HTTP_PROXY'] = settings.HTTP_PROXY
if settings.HTTPS_PROXY:
    os.environ['HTTPS_PROXY'] = settings.HTTPS_PROXY
if settings.NO_PROXY:
    os.environ['NO_PROXY'] = settings.NO_PROXY


def get_settings() -> Settings:
    """获取配置实例"""
    return settings

"""
 zhitouagent FastAPI Backend
主应用程序入口

Copyright (c) 2025 hsliuping. All rights reserved.
版权所有 (c) 2025 hsliuping。保留所有权利。

This software is proprietary and confidential. Unauthorized copying, distribution,
or use of this software, via any medium, is strictly prohibited.
本软件为专有和机密软件。严禁通过任何媒介未经授权复制、分发或使用本软件。

For support, please contact: zh75067197@gmail.com
技术支持请联系：zh75067197@gmail.com
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
import time
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
import os

# 新部署使用 ZHITOUAGENT_*；旧部署变量仅作为读取兼容，不再写回或展示。
for _key, _value in list(os.environ.items()):
    if _key.startswith("TRADINGAGENTS_"):
        os.environ.setdefault("ZHITOUAGENT_" + _key[len("TRADINGAGENTS_"):], _value)

# 加载 .env.local（如果存在），覆盖 .env 中的同名变量
# 用途：本地开发时设置 WXPAY_MOCK=true 等，不影响生产 .env
try:
    from dotenv import load_dotenv as _load_dotenv
    _local_env = Path(__file__).parent.parent / ".env.local"
    if _local_env.exists():
        _load_dotenv(_local_env, override=True)
except ImportError:
    pass

from app.core.config import settings
from app.core.database import init_db, close_db, get_mongo_db
from app.core.logging_config import setup_logging
from app.routers import auth_db as auth, analysis, screening, queue, sse, health, favorites, config, reports, database, operation_logs, tags, tushare_init, akshare_init, baostock_init, historical_data, multi_period_sync, financial_data, news_data, social_media, internal_messages, usage_statistics, model_capabilities, cache, logs
from app.routers import vibe_agent as vibe_agent_router
from app.routers import decision_audit as decision_audit_router
from app.routers import sync as sync_router, multi_source_sync
from app.routers import stocks as stocks_router
from app.routers import stock_data as stock_data_router
from app.routers import stock_sync as stock_sync_router
from app.routers import multi_market_stocks as multi_market_stocks_router
from app.routers import notifications as notifications_router
from app.routers import websocket_notifications as websocket_notifications_router
from app.routers import scheduler as scheduler_router
from app.routers import personal_investment as personal_investment_router
from app.routers import news_watch as news_watch_router
from app.routers import token_billing as token_billing_router
from app.services.basics_sync_service import get_basics_sync_service
from app.services.multi_source_basics_sync_service import MultiSourceBasicsSyncService
from app.services.scheduler_service import set_scheduler_instance
from app.worker.tushare_sync_service import (
    run_tushare_basic_info_sync,
    run_tushare_quotes_sync,
    run_tushare_historical_sync,
    run_tushare_financial_sync,
    run_tushare_status_check
)
from app.worker.akshare_sync_service import (
    run_akshare_basic_info_sync,
    run_akshare_quotes_sync,
    run_akshare_historical_sync,
    run_akshare_financial_sync,
    run_akshare_status_check
)
from app.worker.baostock_sync_service import (
    run_baostock_basic_info_sync,
    run_baostock_daily_quotes_sync,
    run_baostock_historical_sync,
    run_baostock_status_check
)
# 港股和美股改为按需获取+缓存模式，不再需要定时同步任务
# from app.worker.hk_sync_service import ...
# from app.worker.us_sync_service import ...
from app.middleware.operation_log_middleware import OperationLogMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.services.quotes_ingestion_service import QuotesIngestionService
from app.routers import paper as paper_router


def get_version() -> str:
    """从 VERSION 文件读取版本号"""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return "1.0.0"  # 默认版本号


async def _print_config_summary(logger):
    """显示配置摘要"""
    try:
        logger.info("=" * 70)
        logger.info("📋 zhitouagent Configuration Summary")
        logger.info("=" * 70)

        # .env 文件路径信息
        import os
        from pathlib import Path
        
        current_dir = Path.cwd()
        logger.info(f"📁 Current working directory: {current_dir}")
        
        # 检查可能的 .env 文件位置
        env_files_to_check = [
            current_dir / ".env",
            current_dir / "app" / ".env",
            Path(__file__).parent.parent / ".env",  # 项目根目录
        ]
        
        logger.info("🔍 Checking .env file locations:")
        env_file_found = False
        for env_file in env_files_to_check:
            if env_file.exists():
                logger.info(f"  ✅ Found: {env_file} (size: {env_file.stat().st_size} bytes)")
                env_file_found = True
                # 显示文件的前几行（隐藏敏感信息）
                try:
                    with open(env_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[:5]  # 只读前5行
                        logger.info(f"     Preview (first 5 lines):")
                        for i, line in enumerate(lines, 1):
                            # 隐藏包含密码、密钥等敏感信息的行
                            if any(keyword in line.upper() for keyword in ['PASSWORD', 'SECRET', 'KEY', 'TOKEN']):
                                logger.info(f"       {i}: {line.split('=')[0]}=***")
                            else:
                                logger.info(f"       {i}: {line.strip()}")
                except Exception as e:
                    logger.warning(f"     Could not preview file: {e}")
            else:
                logger.info(f"  ❌ Not found: {env_file}")
        
        if not env_file_found:
            logger.warning("⚠️  No .env file found in checked locations")
        
        # Pydantic Settings 配置加载状态
        logger.info("⚙️  Pydantic Settings Configuration:")
        logger.info(f"  • Settings class: {settings.__class__.__name__}")
        logger.info(f"  • Config source: {getattr(settings.model_config, 'env_file', 'Not specified')}")
        logger.info(f"  • Encoding: {getattr(settings.model_config, 'env_file_encoding', 'Not specified')}")
        
        # 显示一些关键配置值的来源（环境变量 vs 默认值）
        key_settings = ['HOST', 'PORT', 'DEBUG', 'MONGODB_HOST', 'REDIS_HOST']
        logger.info("  • Key settings sources:")
        for setting_name in key_settings:
            env_var_name = setting_name
            env_value = os.getenv(env_var_name)
            config_value = getattr(settings, setting_name, None)
            if env_value is not None:
                logger.info(f"    - {setting_name}: from environment variable ({config_value})")
            else:
                logger.info(f"    - {setting_name}: using default value ({config_value})")
        
        # 环境信息
        env = "Production" if settings.is_production else "Development"
        logger.info(f"Environment: {env}")

        # 数据库连接
        logger.info(f"MongoDB: {settings.MONGODB_HOST}:{settings.MONGODB_PORT}/{settings.MONGODB_DATABASE}")
        logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")

        # 代理配置
        import os
        if settings.HTTP_PROXY or settings.HTTPS_PROXY:
            logger.info("Proxy Configuration:")
            if settings.HTTP_PROXY:
                logger.info(f"  HTTP_PROXY: {settings.HTTP_PROXY}")
            if settings.HTTPS_PROXY:
                logger.info(f"  HTTPS_PROXY: {settings.HTTPS_PROXY}")
            if settings.NO_PROXY:
                # 只显示前3个域名
                no_proxy_list = settings.NO_PROXY.split(',')
                if len(no_proxy_list) <= 3:
                    logger.info(f"  NO_PROXY: {settings.NO_PROXY}")
                else:
                    logger.info(f"  NO_PROXY: {','.join(no_proxy_list[:3])}... ({len(no_proxy_list)} domains)")
            logger.info(f"  ✅ Proxy environment variables set successfully")
        else:
            logger.info("Proxy: Not configured (direct connection)")

        # 检查大模型配置
        try:
            from app.services.config_service import config_service
            config = await config_service.get_system_config()
            if config and config.llm_configs:
                enabled_llms = [llm for llm in config.llm_configs if llm.enabled]
                logger.info(f"Enabled LLMs: {len(enabled_llms)}")
                if enabled_llms:
                    for llm in enabled_llms[:3]:  # 只显示前3个
                        logger.info(f"  • {llm.provider}: {llm.model_name}")
                    if len(enabled_llms) > 3:
                        logger.info(f"  • ... and {len(enabled_llms) - 3} more")
                else:
                    logger.warning("⚠️  No LLM enabled. Please configure at least one LLM in Web UI.")
            else:
                logger.warning("⚠️  No LLM configured. Please configure at least one LLM in Web UI.")
        except Exception as e:
            logger.warning(f"⚠️  Failed to check LLM configs: {e}")

        # 检查数据源配置
        try:
            if config and config.data_source_configs:
                enabled_sources = [ds for ds in config.data_source_configs if ds.enabled]
                logger.info(f"Enabled Data Sources: {len(enabled_sources)}")
                if enabled_sources:
                    for ds in enabled_sources[:3]:  # 只显示前3个
                        logger.info(f"  • {ds.type.value}: {ds.name}")
                    if len(enabled_sources) > 3:
                        logger.info(f"  • ... and {len(enabled_sources) - 3} more")
            else:
                logger.info("Data Sources: Using default (AKShare)")
        except Exception as e:
            logger.warning(f"⚠️  Failed to check data source configs: {e}")

        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"Failed to print config summary: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    setup_logging()
    logger = logging.getLogger("app.main")

    # 验证启动配置
    try:
        from app.core.startup_validator import validate_startup_config
        validate_startup_config()
    except Exception as e:
        logger.error(f"配置验证失败: {e}")
        raise

    await init_db()

    # 受控管理员初始化：只有显式提供强初始密码时才创建管理员
    try:
        from app.services.user_service import user_service
        existing_admin = await user_service.get_user_by_username("admin")
        initial_admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
        if existing_admin:
            logger.info("ℹ️ 管理员账号已存在，跳过初始化")
        elif initial_admin_password:
            password_error = user_service.validate_password(initial_admin_password)
            if password_error:
                logger.warning("管理员初始化失败：初始密码不符合策略，请通过受控渠道重试")
            else:
                admin_user = await user_service.create_admin_user(
                    username="admin",
                    password=initial_admin_password,
                    email="zh75067197@gmail.com"
                )
                if admin_user:
                    logger.info("✅ 管理员账号初始化完成")
                else:
                    logger.warning("⚠️ 管理员账号初始化失败")
        else:
            logger.warning("未配置 INITIAL_ADMIN_PASSWORD，跳过自动创建管理员；请使用 scripts/create_default_admin.py 受控初始化")
    except Exception as e:
        logger.warning(f"⚠️ 管理员初始化检查失败（非阻塞）: {e}")

    try:
        from app.services.personal_investment.profile_service import profile_service
        from app.services.personal_investment.strategy_service import strategy_service
        from app.services.personal_investment.task_service import task_service

        await profile_service.initialize()
        await strategy_service.initialize()
        await task_service.initialize()

        from app.services.personal_investment.marketplace_service import marketplace_service
        await marketplace_service.initialize()
        await marketplace_service.seed_builtin_templates()

        # 数据就绪服务
        from app.services.data_readiness_service import get_data_readiness_service
        data_readiness = await get_data_readiness_service()
        try:
            await data_readiness.refresh()
        except Exception as e:
            logger.warning(f"初始数据就绪检查失败（非阻塞）: {e}")

        # 策略模拟服务
        if settings.SIMULATION_ENABLED:
            from app.services.simulation_service import get_simulation_service
            await get_simulation_service()

        # 观察标的服务
        from app.services.personal_investment.observation_service import observation_service
        await observation_service.initialize()

        # 新闻智能闭环服务
        from app.services.news_aggregator_service import get_news_aggregator_service
        await get_news_aggregator_service()
        from app.services.news_impact_agent_service import get_news_impact_agent_service
        await get_news_impact_agent_service()
        from app.services.news_closed_loop_service import get_news_closed_loop_service
        await get_news_closed_loop_service()

        logger.info("✅ 个人投资助手服务已初始化")
    except Exception as e:
        logger.warning(f"个人投资助手初始化失败: {e}")

    try:
        from app.services.vibe_agent.service import vibe_agent_service
        await vibe_agent_service.ensure_indexes()
        from app.core.ownership import ensure_owner_indexes
        await ensure_owner_indexes(get_mongo_db())
    except Exception as e:
        logger.warning(f"Vibe Agent 索引初始化失败: {e}")

    # 初始化 Agent 评测平台服务
    try:
        from app.services.eval.dataset_service import dataset_service
        from app.services.eval.runner_service import runner_service
        from app.services.eval.trace_adapter import trace_adapter
        from app.services.eval.scorer_hub import scorer_hub
        from app.services.eval.bad_case_service import bad_case_service

        await dataset_service.initialize()
        await runner_service.initialize()
        await trace_adapter.initialize()
        await scorer_hub.initialize()
        from app.services.eval.skill_regression_service import skill_regression_service
        await skill_regression_service.initialize()
        await bad_case_service.initialize()
        logger.info("✅ Agent 评测平台服务已初始化")
    except Exception as e:
        logger.warning(f"Agent 评测平台初始化失败: {e}")

    # 初始化 Agent 自进化服务
    try:
        from app.services.evolution.artifact_registry import artifact_registry
        from app.services.evolution.trigger_service import trigger_service
        from app.services.evolution.proposal_service import proposal_service
        from app.services.evolution.verification_service import verification_service
        from app.services.evolution.approval_service import approval_service
        from app.services.evolution.receipt_service import receipt_service
        from app.services.evolution.governance_service import governance_service

        await artifact_registry.initialize()
        await trigger_service.initialize()
        await proposal_service.initialize()
        await verification_service.initialize()
        await approval_service.initialize()
        await receipt_service.initialize()
        await governance_service.initialize()
        logger.info("✅ Agent 自进化服务已初始化")
    except Exception as e:
        logger.warning(f"Agent 自进化服务初始化失败: {e}")

    # Token 计费模块初始化（种子数据 + 默认配置）
    try:
        from app.services.token_billing_service import init_token_billing
        await init_token_billing()
    except Exception as e:
        logger.warning(f"⚠️ Token计费模块初始化失败: {e}")

    #  配置桥接：将统一配置写入环境变量，供 zhitouagent 核心库使用
    try:
        from app.core.config_bridge import bridge_config_to_env
        bridge_config_to_env()
    except Exception as e:
        logger.warning(f"⚠️  配置桥接失败: {e}")
        logger.warning("⚠️  zhitouagent 将使用 .env 文件中的配置")

    # Apply dynamic settings (log_level, enable_monitoring) from ConfigProvider
    try:
        from app.services.config_provider import provider as config_provider  # local import to avoid early DB init issues
        eff = await config_provider.get_effective_system_settings()
        desired_level = str(eff.get("log_level", "INFO")).upper()
        setup_logging(log_level=desired_level)
        for name in ("webapi", "worker", "uvicorn", "fastapi"):
            logging.getLogger(name).setLevel(desired_level)
        try:
            from app.middleware.operation_log_middleware import set_operation_log_enabled
            set_operation_log_enabled(bool(eff.get("enable_monitoring", True)))
        except Exception:
            pass
    except Exception as e:
        logging.getLogger("webapi").warning(f"Failed to apply dynamic settings: {e}")

    # 显示配置摘要
    await _print_config_summary(logger)

    logger.info("zhitouagent FastAPI backend started")

    # 启动期：若需要在休市时补充上一交易日收盘快照
    if settings.QUOTES_BACKFILL_ON_STARTUP:
        try:
            qi = QuotesIngestionService()
            await qi.ensure_indexes()
            await qi.backfill_last_close_snapshot_if_needed()
        except Exception as e:
            logger.warning(f"Startup backfill failed (ignored): {e}")

    # 启动每日定时任务：可配置
    scheduler: AsyncIOScheduler | None = None
    try:
        from croniter import croniter
    except Exception:
        croniter = None  # 可选依赖
    try:
        scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

        # 使用多数据源同步服务（支持自动切换）
        multi_source_service = MultiSourceBasicsSyncService()

        # 根据 TUSHARE_ENABLED 配置决定优先数据源
        # 如果 Tushare 被禁用，系统会自动使用其他可用数据源（AKShare/BaoStock）
        preferred_sources = None  # None 表示使用默认优先级顺序

        if settings.TUSHARE_ENABLED:
            # Tushare 启用时，优先使用 Tushare
            preferred_sources = ["tushare", "akshare", "baostock"]
            logger.info(f"📊 股票基础信息同步优先数据源: Tushare > AKShare > BaoStock")
        else:
            # Tushare 禁用时，使用 AKShare 和 BaoStock
            preferred_sources = ["akshare", "baostock"]
            logger.info(f"📊 股票基础信息同步优先数据源: AKShare > BaoStock (Tushare已禁用)")

        # 立即在启动后尝试一次（不阻塞）
        async def run_sync_with_sources():
            await multi_source_service.run_full_sync(force=False, preferred_sources=preferred_sources)

        asyncio.create_task(run_sync_with_sources())

        # 配置调度：优先使用 CRON，其次使用 HH:MM
        if settings.SYNC_STOCK_BASICS_ENABLED:
            if settings.SYNC_STOCK_BASICS_CRON:
                # 如果提供了cron表达式
                scheduler.add_job(
                    lambda: multi_source_service.run_full_sync(force=False, preferred_sources=preferred_sources),
                    CronTrigger.from_crontab(settings.SYNC_STOCK_BASICS_CRON, timezone=settings.TIMEZONE),
                    id="basics_sync_service",
                    name="股票基础信息同步（多数据源）"
                )
                logger.info(f"📅 Stock basics sync scheduled by CRON: {settings.SYNC_STOCK_BASICS_CRON} ({settings.TIMEZONE})")
            else:
                hh, mm = (settings.SYNC_STOCK_BASICS_TIME or "06:30").split(":")
                scheduler.add_job(
                    lambda: multi_source_service.run_full_sync(force=False, preferred_sources=preferred_sources),
                    CronTrigger(hour=int(hh), minute=int(mm), timezone=settings.TIMEZONE),
                    id="basics_sync_service",
                    name="股票基础信息同步（多数据源）"
                )
                logger.info(f"📅 Stock basics sync scheduled daily at {settings.SYNC_STOCK_BASICS_TIME} ({settings.TIMEZONE})")

        # 实时行情入库任务（每N秒），内部自判交易时段
        if settings.QUOTES_INGEST_ENABLED:
            quotes_ingestion = QuotesIngestionService()
            await quotes_ingestion.ensure_indexes()
            scheduler.add_job(
                quotes_ingestion.run_once,  # coroutine function; AsyncIOScheduler will await it
                IntervalTrigger(seconds=settings.QUOTES_INGEST_INTERVAL_SECONDS, timezone=settings.TIMEZONE),
                id="quotes_ingestion_service",
                name="实时行情入库服务"
            )
            logger.info(f"⏱ 实时行情入库任务已启动: 每 {settings.QUOTES_INGEST_INTERVAL_SECONDS}s")

        # Tushare统一数据同步任务配置
        logger.info("🔄 配置Tushare统一数据同步任务...")

        # 基础信息同步任务
        scheduler.add_job(
            run_tushare_basic_info_sync,
            CronTrigger.from_crontab(settings.TUSHARE_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_basic_info_sync",
            name="股票基础信息同步（Tushare）",
            kwargs={"force_update": False}
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("tushare_basic_info_sync")
            logger.info(f"⏸️ Tushare基础信息同步已添加但暂停: {settings.TUSHARE_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"📅 Tushare基础信息同步已配置: {settings.TUSHARE_BASIC_INFO_SYNC_CRON}")

        # 实时行情同步任务
        scheduler.add_job(
            run_tushare_quotes_sync,
            CronTrigger.from_crontab(settings.TUSHARE_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_quotes_sync",
            name="实时行情同步（Tushare）"
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("tushare_quotes_sync")
            logger.info(f"⏸️ Tushare行情同步已添加但暂停: {settings.TUSHARE_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"📈 Tushare行情同步已配置: {settings.TUSHARE_QUOTES_SYNC_CRON}")

        # 历史数据同步任务
        scheduler.add_job(
            run_tushare_historical_sync,
            CronTrigger.from_crontab(settings.TUSHARE_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_historical_sync",
            name="历史数据同步（Tushare）",
            kwargs={"incremental": True}
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("tushare_historical_sync")
            logger.info(f"⏸️ Tushare历史数据同步已添加但暂停: {settings.TUSHARE_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"📊 Tushare历史数据同步已配置: {settings.TUSHARE_HISTORICAL_SYNC_CRON}")

        # 财务数据同步任务
        scheduler.add_job(
            run_tushare_financial_sync,
            CronTrigger.from_crontab(settings.TUSHARE_FINANCIAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_financial_sync",
            name="财务数据同步（Tushare）"
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_FINANCIAL_SYNC_ENABLED):
            scheduler.pause_job("tushare_financial_sync")
            logger.info(f"⏸️ Tushare财务数据同步已添加但暂停: {settings.TUSHARE_FINANCIAL_SYNC_CRON}")
        else:
            logger.info(f"💰 Tushare财务数据同步已配置: {settings.TUSHARE_FINANCIAL_SYNC_CRON}")

        # 状态检查任务
        scheduler.add_job(
            run_tushare_status_check,
            CronTrigger.from_crontab(settings.TUSHARE_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="tushare_status_check",
            name="数据源状态检查（Tushare）"
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_STATUS_CHECK_ENABLED):
            scheduler.pause_job("tushare_status_check")
            logger.info(f"⏸️ Tushare状态检查已添加但暂停: {settings.TUSHARE_STATUS_CHECK_CRON}")
        else:
            logger.info(f"🔍 Tushare状态检查已配置: {settings.TUSHARE_STATUS_CHECK_CRON}")

        # AKShare统一数据同步任务配置
        logger.info("🔄 配置AKShare统一数据同步任务...")

        # 基础信息同步任务
        scheduler.add_job(
            run_akshare_basic_info_sync,
            CronTrigger.from_crontab(settings.AKSHARE_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_basic_info_sync",
            name="股票基础信息同步（AKShare）",
            kwargs={"force_update": False}
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("akshare_basic_info_sync")
            logger.info(f"⏸️ AKShare基础信息同步已添加但暂停: {settings.AKSHARE_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"📅 AKShare基础信息同步已配置: {settings.AKSHARE_BASIC_INFO_SYNC_CRON}")

        # 实时行情同步任务
        scheduler.add_job(
            run_akshare_quotes_sync,
            CronTrigger.from_crontab(settings.AKSHARE_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_quotes_sync",
            name="实时行情同步（AKShare）"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("akshare_quotes_sync")
            logger.info(f"⏸️ AKShare行情同步已添加但暂停: {settings.AKSHARE_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"📈 AKShare行情同步已配置: {settings.AKSHARE_QUOTES_SYNC_CRON}")

        # 历史数据同步任务
        scheduler.add_job(
            run_akshare_historical_sync,
            CronTrigger.from_crontab(settings.AKSHARE_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_historical_sync",
            name="历史数据同步（AKShare）",
            kwargs={"incremental": True}
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("akshare_historical_sync")
            logger.info(f"⏸️ AKShare历史数据同步已添加但暂停: {settings.AKSHARE_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"📊 AKShare历史数据同步已配置: {settings.AKSHARE_HISTORICAL_SYNC_CRON}")

        # 财务数据同步任务
        scheduler.add_job(
            run_akshare_financial_sync,
            CronTrigger.from_crontab(settings.AKSHARE_FINANCIAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_financial_sync",
            name="财务数据同步（AKShare）"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_FINANCIAL_SYNC_ENABLED):
            scheduler.pause_job("akshare_financial_sync")
            logger.info(f"⏸️ AKShare财务数据同步已添加但暂停: {settings.AKSHARE_FINANCIAL_SYNC_CRON}")
        else:
            logger.info(f"💰 AKShare财务数据同步已配置: {settings.AKSHARE_FINANCIAL_SYNC_CRON}")

        # 状态检查任务
        scheduler.add_job(
            run_akshare_status_check,
            CronTrigger.from_crontab(settings.AKSHARE_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="akshare_status_check",
            name="数据源状态检查（AKShare）"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_STATUS_CHECK_ENABLED):
            scheduler.pause_job("akshare_status_check")
            logger.info(f"⏸️ AKShare状态检查已添加但暂停: {settings.AKSHARE_STATUS_CHECK_CRON}")
        else:
            logger.info(f"🔍 AKShare状态检查已配置: {settings.AKSHARE_STATUS_CHECK_CRON}")

        # BaoStock统一数据同步任务配置
        logger.info("🔄 配置BaoStock统一数据同步任务...")

        # 基础信息同步任务
        scheduler.add_job(
            run_baostock_basic_info_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_basic_info_sync",
            name="股票基础信息同步（BaoStock）"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("baostock_basic_info_sync")
            logger.info(f"⏸️ BaoStock基础信息同步已添加但暂停: {settings.BAOSTOCK_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"📋 BaoStock基础信息同步已配置: {settings.BAOSTOCK_BASIC_INFO_SYNC_CRON}")

        # 日K线同步任务（注意：BaoStock不支持实时行情）
        scheduler.add_job(
            run_baostock_daily_quotes_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_daily_quotes_sync",
            name="日K线数据同步（BaoStock）"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_DAILY_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("baostock_daily_quotes_sync")
            logger.info(f"⏸️ BaoStock日K线同步已添加但暂停: {settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"📈 BaoStock日K线同步已配置: {settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON} (注意：BaoStock不支持实时行情)")

        # 历史数据同步任务
        scheduler.add_job(
            run_baostock_historical_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_historical_sync",
            name="历史数据同步（BaoStock）"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("baostock_historical_sync")
            logger.info(f"⏸️ BaoStock历史数据同步已添加但暂停: {settings.BAOSTOCK_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"📊 BaoStock历史数据同步已配置: {settings.BAOSTOCK_HISTORICAL_SYNC_CRON}")

        # 状态检查任务
        scheduler.add_job(
            run_baostock_status_check,
            CronTrigger.from_crontab(settings.BAOSTOCK_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="baostock_status_check",
            name="数据源状态检查（BaoStock）"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_STATUS_CHECK_ENABLED):
            scheduler.pause_job("baostock_status_check")
            logger.info(f"⏸️ BaoStock状态检查已添加但暂停: {settings.BAOSTOCK_STATUS_CHECK_CRON}")
        else:
            logger.info(f"🔍 BaoStock状态检查已配置: {settings.BAOSTOCK_STATUS_CHECK_CRON}")

        # 新闻数据同步任务配置（使用AKShare同步所有股票新闻）
        logger.info("🔄 配置新闻数据同步任务...")

        from app.worker.akshare_sync_service import get_akshare_sync_service

        async def run_news_sync():
            """运行新闻同步任务 - 使用AKShare同步自选股新闻"""
            try:
                logger.info("📰 开始新闻数据同步（AKShare - 仅自选股）...")
                service = await get_akshare_sync_service()
                result = await service.sync_news_data(
                    symbols=None,  # None + favorites_only=True 表示只同步自选股
                    max_news_per_stock=settings.NEWS_SYNC_MAX_PER_SOURCE,
                    favorites_only=True  # 只同步自选股
                )
                logger.info(
                    f"✅ 新闻同步完成: "
                    f"处理{result['total_processed']}只自选股, "
                    f"成功{result['success_count']}只, "
                    f"失败{result['error_count']}只, "
                    f"新闻总数{result['news_count']}条, "
                    f"耗时{(datetime.utcnow() - result['start_time']).total_seconds():.2f}秒"
                )
            except Exception as e:
                logger.error(f"❌ 新闻同步失败: {e}", exc_info=True)

        # ==================== 港股/美股数据配置 ====================
        # 港股和美股采用按需获取+缓存模式，不再配置定时同步任务
        logger.info("🇭🇰 港股数据采用按需获取+缓存模式")
        logger.info("🇺🇸 美股数据采用按需获取+缓存模式")

        scheduler.add_job(
            run_news_sync,
            CronTrigger.from_crontab(settings.NEWS_SYNC_CRON, timezone=settings.TIMEZONE),
            id="news_sync",
            name="新闻数据同步（AKShare - 仅自选股）"
        )
        if not settings.NEWS_SYNC_ENABLED:
            scheduler.pause_job("news_sync")
            logger.info(f"⏸️ 新闻数据同步已添加但暂停: {settings.NEWS_SYNC_CRON}")
        else:
            logger.info(f"📰 新闻数据同步已配置（仅自选股）: {settings.NEWS_SYNC_CRON}")

        # 数据就绪状态定期刷新
        async def run_data_readiness_refresh():
            try:
                from app.services.data_readiness_service import get_data_readiness_service
                dr = await get_data_readiness_service()
                await dr.refresh()
            except Exception as e:
                logger.warning(f"数据就绪刷新失败: {e}")

        scheduler.add_job(
            run_data_readiness_refresh,
            CronTrigger.from_crontab(settings.DATA_READINESS_REFRESH_CRON, timezone=settings.TIMEZONE),
            id="data_readiness_refresh",
            name="数据就绪状态刷新",
        )
        if not settings.DATA_READINESS_ENABLED:
            scheduler.pause_job("data_readiness_refresh")
            logger.info(f"⏸️ 数据就绪刷新已添加但暂停")
        else:
            logger.info(f"📊 数据就绪刷新已配置: {settings.DATA_READINESS_REFRESH_CRON}")

        # 策略自动模拟（收盘后运行）
        async def run_auto_simulations():
            try:
                from app.services.simulation_service import get_simulation_service
                from app.services.personal_investment.marketplace_service import marketplace_service
                from app.core.config import get_settings as _gs
                _settings = _gs()
                sim_svc = await get_simulation_service()
                db = __import__("app.core.database", fromlist=["get_mongo_db"]).get_mongo_db()

                # 获取所有已上架模板
                cursor = db[marketplace_service.COLLECTION_TEMPLATES].find({"status": "published"})
                async for tpl in cursor:
                    template_id = tpl.get("template_id", "")
                    screening_criteria = tpl.get("screening_criteria", {})

                    # 按策略条件动态筛选股票池
                    query = {}
                    if screening_criteria:
                        query["$or"] = [
                            {"market_info.market": "CN"},
                            {"category": "stock_cn"},
                        ]
                    pool_cursor = db["stock_basic_info"].find(query).limit(200)
                    stock_pool = []
                    async for doc in pool_cursor:
                        code = doc.get("code", "")
                        if code:
                            stock_pool.append(code)

                    if not stock_pool:
                        continue

                    end_date = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
                    start_date = (__import__("datetime").datetime.now() - __import__("datetime").timedelta(days=_settings.SIMULATION_DEFAULT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

                    from app.services.simulation_service import SimulationConfig
                    config = SimulationConfig(
                        stock_pool=stock_pool[:100],  # 限制规模
                        start_date=start_date,
                        end_date=end_date,
                        rebalance_frequency="monthly",
                    )
                    result = await sim_svc.run_simulation(template_id, config)
                    await sim_svc.update_template_metrics(template_id, result)
                    logger.info(f"Auto simulation for {template_id}: return={result.cumulative_return:.2%}")

            except Exception as e:
                logger.error(f"自动模拟任务失败: {e}", exc_info=True)

        scheduler.add_job(
            run_auto_simulations,
            CronTrigger.from_crontab(settings.SIMULATION_AUTO_RUN_CRON, timezone=settings.TIMEZONE),
            id="auto_simulation",
            name="策略自动模拟",
        )
        if not settings.SIMULATION_ENABLED:
            scheduler.pause_job("auto_simulation")
            logger.info(f"⏸️ 策略自动模拟已添加但暂停")
        else:
            logger.info(f"📈 策略自动模拟已配置: {settings.SIMULATION_AUTO_RUN_CRON}")

        # 自进化定时检查（必须显式配置 cron）
        if settings.EVOLUTION_SCHEDULE_CRON:
            async def run_evolution_scheduled_check():
                try:
                    from app.services.evolution.trigger_service import trigger_service
                    from app.services.evolution.proposal_service import proposal_service
                    trigger_info = await trigger_service.scheduled_check()
                    if trigger_info:
                        await proposal_service.create_from_trigger(trigger_info)
                except Exception as e:
                    logger.warning(f"自进化定时检查失败: {e}")

            scheduler.add_job(
                run_evolution_scheduled_check,
                CronTrigger.from_crontab(settings.EVOLUTION_SCHEDULE_CRON, timezone=settings.TIMEZONE),
                id="evolution_scheduled_check",
                name="自进化定时检查",
            )
            logger.info(f"🧬 自进化定时检查已配置: {settings.EVOLUTION_SCHEDULE_CRON}")
        else:
            logger.info("⏸️ 自进化定时检查未启用")

        # Token计费：每5分钟对账补偿（释放僵死frozen）
        async def _reconcile_token_billing():
            try:
                from app.services.token_billing_service import token_billing_service
                count = await token_billing_service.reconcile_stale_frozen()
                if count > 0:
                    logger.info(f"🔄 Token计费对账: 释放 {count} 个僵死账户")
            except Exception as e:
                logger.warning(f"⚠️ Token计费对账失败: {e}")

        scheduler.add_job(
            _reconcile_token_billing,
            "interval",
            minutes=5,
            id="token_billing_reconcile",
            name="Token计费对账补偿",
            replace_existing=True,
        )
        logger.info("💰 Token计费对账任务已配置: 每5分钟")

        # Token计费：每2分钟清理过期订单
        async def _expire_stale_orders():
            try:
                from app.services.token_billing_service import token_billing_service
                count = await token_billing_service.expire_stale_orders()
                if count > 0:
                    logger.info(f"⏰ 订单过期清理: {count} 个订单已标记expired")
            except Exception as e:
                logger.warning(f"⚠️ 订单过期清理失败: {e}")

        scheduler.add_job(
            _expire_stale_orders,
            "interval",
            minutes=2,
            id="token_order_expiry",
            name="Token订单过期清理",
            replace_existing=True,
        )
        logger.info("⏰ Token订单过期清理任务已配置: 每2分钟")

        scheduler.start()

        # 设置调度器实例到服务中，以便API可以管理任务
        set_scheduler_instance(scheduler)
        logger.info("✅ 调度器服务已初始化")
    except Exception as e:
        logger.error(f"❌ 调度器启动失败: {e}", exc_info=True)
        raise  # 抛出异常，阻止应用启动

    try:
        yield
    finally:
        # 关闭时清理
        if scheduler:
            try:
                scheduler.shutdown(wait=False)
                logger.info("🛑 Scheduler stopped")
            except Exception as e:
                logger.warning(f"Scheduler shutdown error: {e}")

        # 关闭 UserService MongoDB 连接
        try:
            from app.services.user_service import user_service
            user_service.close()
        except Exception as e:
            logger.warning(f"UserService cleanup error: {e}")

        await close_db()
        logger.info("zhitouagent FastAPI backend stopped")


# 创建FastAPI应用
app = FastAPI(
    title="zhitouagent API",
    description="股票分析与批量队列系统 API",
    version=get_version(),
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# 安全中间件
if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS
    )

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# 操作日志中间件
app.add_middleware(OperationLogMiddleware)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # 跳过健康检查和静态文件请求的日志
    if request.url.path in ["/health", "/favicon.ico"] or request.url.path.startswith("/static"):
        response = await call_next(request)
        return response

    # 使用webapi logger记录请求
    logger = logging.getLogger("webapi")
    logger.info(f"🔄 {request.method} {request.url.path} - 开始处理")

    response = await call_next(request)
    process_time = time.time() - start_time

    # 记录请求完成
    status_emoji = "✅" if response.status_code < 400 else "❌"
    logger.info(f"{status_emoji} {request.method} {request.url.path} - 状态: {response.status_code} - 耗时: {process_time:.3f}s")

    return response


# 全局异常处理
# 请求ID/Trace-ID 中间件（需作为最外层，放在函数式中间件之后）
from app.middleware.request_id import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error occurred",
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )


# 测试端点 - 验证中间件是否工作
@app.get("/api/test-log")
async def test_log():
    """测试日志中间件是否工作"""
    print("🧪 测试端点被调用 - 这条消息应该出现在控制台")
    return {"message": "测试成功", "timestamp": time.time()}

# 注册路由
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(reports.router, tags=["reports"])
app.include_router(screening.router, prefix="/api/screening", tags=["screening"])
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
app.include_router(vibe_agent_router.router, prefix="/api/vibe-agent", tags=["vibe-agent"])
app.include_router(decision_audit_router.router, prefix="/api/decision-audit", tags=["decision-audit"])
app.include_router(personal_investment_router.router, prefix="/api/investment", tags=["personal-investment"])
app.include_router(news_watch_router.router, prefix="/api/news-watch", tags=["news-watch"])
app.include_router(favorites.router, prefix="/api", tags=["favorites"])
app.include_router(stocks_router.router, prefix="/api", tags=["stocks"])
app.include_router(multi_market_stocks_router.router, prefix="/api", tags=["multi-market"])
app.include_router(stock_data_router.router, tags=["stock-data"])
app.include_router(stock_sync_router.router, tags=["stock-sync"])
app.include_router(tags.router, prefix="/api", tags=["tags"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(model_capabilities.router, tags=["model-capabilities"])
app.include_router(usage_statistics.router, tags=["usage-statistics"])
app.include_router(database.router, prefix="/api/system", tags=["database"])
app.include_router(cache.router, tags=["cache"])
app.include_router(operation_logs.router, prefix="/api/system", tags=["operation_logs"])
app.include_router(logs.router, prefix="/api/system", tags=["logs"])
# 新增：系统配置只读摘要
from app.routers import system_config as system_config_router
app.include_router(system_config_router.router, prefix="/api/system", tags=["system"])

# 通知模块（REST + SSE）
app.include_router(notifications_router.router, prefix="/api", tags=["notifications"])

# 🔥 WebSocket 通知模块（替代 SSE + Redis PubSub）
app.include_router(websocket_notifications_router.router, prefix="/api", tags=["websocket"])

# 定时任务管理
app.include_router(scheduler_router.router, tags=["scheduler"])

app.include_router(sse.router, prefix="/api/stream", tags=["streaming"])
app.include_router(sync_router.router)
app.include_router(multi_source_sync.router)
app.include_router(paper_router.router, prefix="/api", tags=["paper"])
app.include_router(token_billing_router.router, prefix="/api", tags=["token-billing"])
app.include_router(tushare_init.router, prefix="/api", tags=["tushare-init"])
app.include_router(akshare_init.router, prefix="/api", tags=["akshare-init"])
app.include_router(baostock_init.router, prefix="/api", tags=["baostock-init"])
app.include_router(historical_data.router, tags=["historical-data"])
app.include_router(multi_period_sync.router, tags=["multi-period-sync"])
app.include_router(financial_data.router, tags=["financial-data"])
app.include_router(news_data.router, tags=["news-data"])
app.include_router(social_media.router, tags=["social-media"])
app.include_router(internal_messages.router, tags=["internal-messages"])

# Agent 评测平台
from app.routers import eval as eval_router
app.include_router(eval_router.router, prefix="/api/eval", tags=["evaluation"])

# Agent 自进化闭环
from app.routers import evolution as evolution_router
app.include_router(evolution_router.router, prefix="/api/evolution", tags=["evolution"])

# 数据就绪状态 API
from app.routers import data_readiness as data_readiness_router
app.include_router(data_readiness_router.router, prefix="/api/system", tags=["data-readiness"])


@app.get("/")
async def root():
    """根路径，返回API信息"""
    print("🏠 根路径被访问")
    return {
        "name": "zhitouagent API",
        "version": get_version(),
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
        reload_dirs=["app"] if settings.DEBUG else None,
        reload_excludes=[
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".git",
            ".pytest_cache",
            "*.log",
            "*.tmp"
        ] if settings.DEBUG else None,
        reload_includes=["*.py"] if settings.DEBUG else None
    )

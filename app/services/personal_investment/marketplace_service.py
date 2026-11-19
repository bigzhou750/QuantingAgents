"""
策略广场服务

管理平台策略模板的上架、查询和复制到用户策略实例。
模板是公共资产，用户策略是私有数据，两者通过 source_template_id 关联。
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from app.core.database import get_mongo_db
from app.models.personal_investment import (
    StrategyTemplate,
    TemplateStatus,
    TemplateSource,
)
from app.services.personal_investment.terminology_filter import TerminologyFilter
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class MarketplaceService:
    """策略广场服务"""

    COLLECTION_TEMPLATES = "strategy_templates"
    COLLECTION_STRATEGIES = "strategy_definitions"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务和索引"""
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION_TEMPLATES].create_index("template_id", unique=True)
        await db[self.COLLECTION_TEMPLATES].create_index("status")
        await db[self.COLLECTION_TEMPLATES].create_index("source")
        await db[self.COLLECTION_TEMPLATES].create_index("tags")
        await db[self.COLLECTION_TEMPLATES].create_index("created_at")
        await db[self.COLLECTION_STRATEGIES].create_index(
            [("user_id", 1), ("source_template_id", 1)]
        )
        self._initialized = True
        logger.info("MarketplaceService initialized")

    # ==================== 模板 CRUD ====================

    async def create_template(
        self,
        name: str,
        one_liner: str = "",
        description: str = "",
        audience: str = "",
        not_for: str = "",
        risk_boundary: str = "",
        data_requirements: str = "",
        rule_explanation: Optional[Dict[str, Any]] = None,
        applicable_markets: Optional[List[str]] = None,
        screening_criteria: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        source: TemplateSource = TemplateSource.BUILTIN,
        author: str = "system",
        auto_publish: bool = False,
    ) -> Dict[str, Any]:
        """创建策略模板

        Args:
            auto_publish: 仅当 True 且合规检查通过时直接上架
        """
        # 合规检查
        compliance = TerminologyFilter.validate_compliance(
            f"{name} {description} {one_liner} {audience} {not_for} "
            f"{risk_boundary} {data_requirements} {rule_explanation or {}}"
        )
        if not compliance.get("compliant", True):
            violations = compliance.get("violations", [])
            terms = [v.get("term", v.get("pattern", "")) for v in violations]
            raise ValueError(f"策略包含不合规措辞: {', '.join(terms)}。请修正后重新提交。")

        if source == TemplateSource.AGENT_DRAFT and auto_publish:
            raise ValueError("Agent 生成的策略只能保存为草稿或待审核状态，不能直接上架")

        if auto_publish:
            missing_fields = [
                label for label, value in (
                    ("一句话说明", one_liner),
                    ("适合人群", audience),
                    ("风险边界", risk_boundary),
                    ("数据要求", data_requirements),
                    ("规则解释", rule_explanation),
                ) if not value
            ]
            if missing_fields:
                raise ValueError(f"模板缺少上架必填字段: {', '.join(missing_fields)}")

        template_id = f"tpl_{uuid.uuid4().hex[:12]}"
        status = TemplateStatus.PUBLISHED if auto_publish else TemplateStatus.DRAFT

        template = StrategyTemplate(
            template_id=template_id,
            name=name,
            one_liner=one_liner,
            description=description,
            status=status,
            source=source,
            author=author,
            audience=audience,
            not_for=not_for,
            risk_boundary=risk_boundary,
            data_requirements=data_requirements,
            rule_explanation=rule_explanation or {},
            applicable_markets=applicable_markets or ["A股"],
            screening_criteria=screening_criteria or {},
            parameters=parameters or {},
            tags=tags or [],
        )

        db = get_mongo_db()
        await db[self.COLLECTION_TEMPLATES].insert_one(template.model_dump(by_alias=True, exclude={"id"}))
        logger.info(f"Created strategy template: {template_id} ({name}), status={status.value}")
        return {"template_id": template_id, "name": name, "status": status.value}

    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """获取模板详情"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_TEMPLATES].find_one({"template_id": template_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def list_published_templates(
        self,
        tag: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """列出已上架的策略模板（普通用户可见）"""
        db = get_mongo_db()
        query: Dict[str, Any] = {"status": TemplateStatus.PUBLISHED.value}
        if tag:
            query["tags"] = tag

        total = await db[self.COLLECTION_TEMPLATES].count_documents(query)
        cursor = (
            db[self.COLLECTION_TEMPLATES]
            .find(query)
            .skip(skip)
            .limit(limit)
            .sort("created_at", -1)
        )
        items = []
        async for doc in cursor:
            doc.pop("_id", None)
            items.append(doc)
        return {"items": items, "count": total}

    async def publish_template(self, template_id: str) -> bool:
        """上架模板（需先通过合规检查）"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_TEMPLATES].find_one({"template_id": template_id})
        if not doc:
            raise ValueError("模板不存在")

        if doc.get("status") not in {
            TemplateStatus.DRAFT.value,
            TemplateStatus.PENDING_REVIEW.value,
        }:
            raise ValueError("只有草稿或待审核模板可以上架")

        required_fields = {
            "一句话说明": doc.get("one_liner"),
            "适合人群": doc.get("audience"),
            "风险边界": doc.get("risk_boundary"),
            "数据要求": doc.get("data_requirements"),
            "规则解释": doc.get("rule_explanation"),
        }
        missing_fields = [label for label, value in required_fields.items() if not value]
        if missing_fields:
            raise ValueError(f"模板缺少上架必填字段: {', '.join(missing_fields)}")

        # 合规检查覆盖所有会面向普通用户展示的解释字段
        text = " ".join(
            str(doc.get(field, ""))
            for field in (
                "name", "description", "one_liner", "audience",
                "not_for", "risk_boundary", "data_requirements",
                "rule_explanation",
            )
        )
        compliance = TerminologyFilter.validate_compliance(text)
        if not compliance.get("compliant", True):
            raise ValueError("模板包含不合规措辞，无法上架")

        result = await db[self.COLLECTION_TEMPLATES].update_one(
            {"template_id": template_id},
            {"$set": {"status": TemplateStatus.PUBLISHED.value, "updated_at": now_tz()}},
        )
        return result.modified_count > 0

    # ==================== 加入我的策略 ====================

    async def adopt_template(self, template_id: str, user_id: str) -> Dict[str, Any]:
        """将策略模板复制为用户策略实例

        Returns:
            新创建的用户策略信息
        Raises:
            ValueError: 模板不存在、未上架、或用户已有相同来源的策略
        """
        db = get_mongo_db()

        # 1. 获取模板
        template = await db[self.COLLECTION_TEMPLATES].find_one({"template_id": template_id})
        if not template:
            raise ValueError("策略模板不存在")
        if template.get("status") != TemplateStatus.PUBLISHED.value:
            raise ValueError("该策略模板未上架")

        # 2. 检查重复
        existing = await db[self.COLLECTION_STRATEGIES].find_one({
            "user_id": user_id,
            "source_template_id": template_id,
            "status": {"$ne": "archived"},
        })
        if existing:
            raise ValueError(f"你已加入过该策略「{existing.get('name', '')}」，可在我的策略中查看")

        # 3. 创建用户策略实例
        from app.services.personal_investment.strategy_service import strategy_service
        strategy_result = await strategy_service.create_strategy(
            user_id=user_id,
            name=template.get("name", ""),
            description=template.get("description", ""),
            applicable_markets=template.get("applicable_markets", ["A股"]),
            screening_criteria=template.get("screening_criteria", {}),
            parameters=template.get("parameters", {}),
            tags=template.get("tags", []),
        )

        # 4. 补充来源追踪字段
        strategy_id = strategy_result.get("strategy_id", "")
        await db[self.COLLECTION_STRATEGIES].update_one(
            {"strategy_id": strategy_id, "user_id": user_id},
            {"$set": {
                "source_template_id": template_id,
                "source_template_version": template.get("version", "1.0.0"),
                "source_type": "marketplace",
                "updated_at": now_tz(),
            }},
        )

        logger.info(f"User {user_id} adopted template {template_id} as strategy {strategy_id}")
        return {
            "strategy_id": strategy_id,
            "name": template.get("name", ""),
            "source_template_id": template_id,
        }

    # ==================== 种子数据 ====================

    async def seed_builtin_templates(self):
        """插入内置策略模板种子数据（幂等）"""
        db = get_mongo_db()
        count = await db[self.COLLECTION_TEMPLATES].count_documents({"source": TemplateSource.BUILTIN.value})
        if count > 0:
            logger.info(f"Builtin templates already seeded ({count} found)")
            return

        builtin_templates = [
            {
                "template_id": "tpl_value_dividend",
                "name": "低估值红利策略",
                "one_liner": "寻找价格偏低、分红稳定的公司，适合追求稳健收益的投资者",
                "description": "通过市盈率、净资产收益率和股息率筛选估值合理且盈利稳定的上市公司。该策略关注企业的内在价值而非短期波动。",
                "audience": "风险承受能力较低、希望获得稳定分红收入的长期投资者",
                "not_for": "追求短期高回报、不愿承受任何回撤的投资者",
                "risk_boundary": "低估值可能是基本面恶化的信号（价值陷阱）；分红可能被削减；市场风格切换时可能长期跑输成长股",
                "data_requirements": "需要最新的财务报表数据和分红记录",
                "rule_explanation": {
                    "pe_max": "市盈率上限——低于此值说明股价相对盈利较便宜",
                    "roe_min": "净资产收益率下限——高于此值说明公司盈利能力较好",
                    "dividend_yield_min": "股息率下限——高于此值说明分红回报较丰厚",
                },
                "applicable_markets": ["A股"],
                "screening_criteria": {"pe_max": 20, "roe_min": 8, "dividend_yield_min": 2},
                "tags": ["value", "dividend", "conservative"],
                "status": TemplateStatus.PUBLISHED.value,
                "source": TemplateSource.BUILTIN.value,
                "author": "system",
                "version": "1.0.0",
            },
            {
                "template_id": "tpl_growth_momentum",
                "name": "成长趋势策略",
                "one_liner": "关注业绩增长快、股价走势向上的公司，适合愿意承担波动的投资者",
                "description": "结合基本面成长指标和技术面趋势信号，筛选处于上升通道的高增长标的。该策略假设趋势会延续，但需要严格止损纪律。",
                "audience": "能承受较大波动、有时间和精力跟踪行情的积极型投资者",
                "not_for": "无法承受20%以上回撤、不关注技术面的投资者",
                "risk_boundary": "趋势反转时可能出现较大亏损；高估值标的一旦业绩不达预期跌幅更大；频繁交易增加成本",
                "data_requirements": "需要实时行情数据和历史K线",
                "rule_explanation": {
                    "pe_max": "市盈率上限——避免追高估值过高的标的",
                    "roe_min": "净资产收益率下限——确保公司有真实的成长能力",
                    "rsi_min": "RSI下限——高于此值说明近期走势偏强",
                    "rsi_max": "RSI上限——低于此值避免追入过热标的",
                    "ma_trend": "均线趋势方向——向上说明中期走势健康",
                },
                "applicable_markets": ["A股"],
                "screening_criteria": {"pe_max": 60, "roe_min": 12, "rsi_min": 40, "rsi_max": 70, "ma_trend": "up"},
                "tags": ["growth", "momentum"],
                "status": TemplateStatus.PUBLISHED.value,
                "source": TemplateSource.BUILTIN.value,
                "author": "system",
                "version": "1.0.0",
            },
            {
                "template_id": "tpl_balanced_start",
                "name": "均衡起步策略",
                "one_liner": "兼顾估值和成长的入门级策略，适合刚开始学习投资的用户",
                "description": "在估值不太贵、盈利不太差的公司中寻找机会。条件相对宽松，帮助新手建立投资框架后再逐步细化。",
                "audience": "刚开始接触股票投资、希望先建立基本认知的新手投资者",
                "not_for": "已有成熟投资体系、追求极致选股精度的资深投资者",
                "risk_boundary": "条件宽松意味着入选标的质量参差不齐；仍需结合个人判断做最终决策；不代表任何收益承诺",
                "data_requirements": "需要基本的财务数据",
                "rule_explanation": {
                    "pe_max": "市盈率上限——排除估值过高的标的",
                    "roe_min": "净资产收益率下限——排除盈利能力太差的公司",
                },
                "applicable_markets": ["A股"],
                "screening_criteria": {"pe_max": 40, "roe_min": 5},
                "tags": ["balanced"],
                "status": TemplateStatus.PUBLISHED.value,
                "source": TemplateSource.BUILTIN.value,
                "author": "system",
                "version": "1.0.0",
            },
        ]

        for tpl_data in builtin_templates:
            # 补全缺失字段
            tpl_data.setdefault("created_at", now_tz())
            tpl_data.setdefault("updated_at", now_tz())
            tpl_data.setdefault("parameters", {})
            tpl_data.setdefault("not_for", "")
            tpl_data.setdefault("data_requirements", "")
            tpl_data.setdefault("rule_explanation", {})

            await db[self.COLLECTION_TEMPLATES].insert_one(tpl_data)

        logger.info(f"Seeded {len(builtin_templates)} builtin strategy templates")


# 模块级单例
marketplace_service = MarketplaceService()

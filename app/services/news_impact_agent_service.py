"""
新闻影响 Agent 分析服务

使用 DashScope LLM 对新闻进行结构化影响分析，输出固定17字段JSON schema。
包含 prompt 模板、schema 校验、规则降级和非交易建议安全过滤。
"""

import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.database import get_mongo_db
from app.models.news_intelligence import (
    NewsAnalysisRecord,
    ANALYSIS_SCHEMA_FIELDS,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

# Prompt 模板 v1
ANALYSIS_PROMPT_TEMPLATE = """你是一位专业的A股市场研究分析师。请对以下新闻进行结构化影响分析。

## 要求
1. 必须以严格的 JSON 格式返回结果
2. 不得给出任何买入、卖出、加仓、减仓等交易建议
3. 仅做客观的研究分析，标注证据强度和不确定性
4. 所有字段都必须填写，不能为 null

## 新闻内容
标题: {title}
内容: {content}
来源: {source}
发布时间: {published_at}
相关标的: {symbol}

## 输出格式（严格JSON）
{{
  "event_summary": "一句话事件摘要",
  "event_type": "业绩|政策|行业|公司|宏观|其他",
  "impact_direction": "positive|negative|neutral",
  "impact_strength": 1到5的整数,
  "time_horizon": "short|medium|long",
  "affected_industries": ["行业1", "行业2"],
  "affected_concepts": ["概念1"],
  "upstream_downstream_paths": ["传导路径描述"],
  "direct_symbols": ["直接相关代码"],
  "indirect_symbols": ["间接相关代码"],
  "portfolio_hits": ["可能影响的持仓"],
  "impact_paths": ["影响传导路径"],
  "evidence_strength": "strong|moderate|weak",
  "market_confirmation": "市场是否已有反应",
  "watch_indicators": ["后续需关注的指标"],
  "uncertainties": ["不确定因素"],
  "non_advisory_note": "本分析仅为研究参考，不构成投资建议"
}}"""


class NewsImpactAgentService:
    """新闻影响 Agent 分析服务"""

    COLLECTION = "news_analysis_results"
    PROMPT_VERSION = "v1"
    SCHEMA_VERSION = "v1"
    DEFAULT_MODEL = "qwen-plus"

    async def initialize(self):
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("created_at")
        await db[self.COLLECTION].create_index("news_ids")
        logger.info("NewsImpactAgentService initialized")

    async def analyze_single(
        self,
        news_item: Dict[str, Any],
    ) -> NewsAnalysisRecord:
        """分析单条新闻"""
        title = news_item.get("title", "")
        content = news_item.get("content", news_item.get("summary", ""))
        source = news_item.get("source", "")
        published_at = news_item.get("published_at", news_item.get("pub_date", ""))
        symbol = news_item.get("symbol", news_item.get("stock_code", ""))

        prompt = self._build_prompt(title, content, source, str(published_at), symbol)

        # 调用 LLM
        raw_output = await self._call_llm(prompt)

        # 校验 schema
        parsed = self._validate_schema(raw_output)

        if parsed is not None:
            # 合规过滤
            filtered = self._apply_compliance_filter(parsed)
            record = NewsAnalysisRecord(
                news_ids=[news_item.get("_id", news_item.get("news_id", ""))],
                prompt_version=self.PROMPT_VERSION,
                schema_version=self.SCHEMA_VERSION,
                model_config=self.DEFAULT_MODEL,
                result=filtered,
                degraded=False,
            )
        else:
            # 规则降级
            fallback = self._rule_based_fallback(news_item)
            record = NewsAnalysisRecord(
                news_ids=[news_item.get("_id", news_item.get("news_id", ""))],
                prompt_version=self.PROMPT_VERSION,
                schema_version=self.SCHEMA_VERSION,
                model_config=self.DEFAULT_MODEL,
                result=fallback,
                degraded=True,
                failure_reason=f"Schema validation failed, raw output: {raw_output[:200]}",
            )

        # 持久化
        await self._persist(record)
        return record

    async def analyze_batch(
        self,
        news_items: List[Dict[str, Any]],
        cluster_first: bool = True,
    ) -> List[NewsAnalysisRecord]:
        """批量分析。cluster_first 时先按 URL/标题/时间窗口聚类，再统一分析。"""
        if cluster_first and news_items:
            from app.services.news_aggregator_service import NewsAggregatorService
            clusters = NewsAggregatorService.cluster_news_items(news_items)
            records = []
            for cluster in clusters:
                representative = cluster["items"][0]
                news_ids = [
                    item.get("_id", item.get("news_id", ""))
                    for item in cluster["items"]
                    if item.get("_id") or item.get("news_id")
                ]
                try:
                    record = await self.analyze_single(representative)
                except Exception as e:
                    logger.error(f"Clustered analysis failed: {e}")
                    record = NewsAnalysisRecord(
                        news_ids=news_ids or [representative.get("_id", "")],
                        degraded=True,
                        failure_reason=str(e)[:200],
                        result=self._rule_based_fallback(representative),
                    )
                    await self._persist(record)
                if news_ids:
                    record.news_ids = news_ids
                    await self._persist(record)
                records.append(record)
            return records

        records = []
        for item in news_items:
            try:
                record = await self.analyze_single(item)
                records.append(record)
            except Exception as e:
                logger.error(f"Batch analysis failed for item: {e}")
                records.append(NewsAnalysisRecord(
                    news_ids=[item.get("_id", "")],
                    degraded=True,
                    failure_reason=str(e)[:200],
                    result=self._rule_based_fallback(item),
                ))
        return records

    async def get_latest_analysis(
        self, news_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取某条新闻的最新分析"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one(
            {"news_ids": news_id},
            sort=[("created_at", -1)],
        )
        if doc:
            doc.pop("_id", None)
        return doc

    # ==================== 内部方法 ====================

    def _build_prompt(
        self, title: str, content: str, source: str,
        published_at: str, symbol: str,
    ) -> str:
        return ANALYSIS_PROMPT_TEMPLATE.format(
            title=title or "无标题",
            content=(content or "无内容")[:2000],  # 限制长度
            source=source or "未知",
            published_at=published_at or "未知",
            symbol=symbol or "未指定",
        )

    async def _call_llm(self, prompt: str) -> str:
        """调用 DashScope LLM"""
        try:
            from dashscope import Generation

            response = Generation.call(
                model=self.DEFAULT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                result_format="message",
                temperature=0.1,
            )

            if response.status_code == 200:
                return response.output.choices[0].message.content
            else:
                raise RuntimeError(
                    f"DashScope API error: {response.code} - {response.message}"
                )

        except ImportError:
            logger.warning("dashscope not available, returning mock output")
            return json.dumps({
                "event_summary": "mock: dashscope unavailable",
                "event_type": "其他",
                "impact_direction": "neutral",
                "impact_strength": 1,
                "time_horizon": "short",
                "affected_industries": [],
                "affected_concepts": [],
                "upstream_downstream_paths": [],
                "direct_symbols": [],
                "indirect_symbols": [],
                "portfolio_hits": [],
                "impact_paths": [],
                "evidence_strength": "weak",
                "market_confirmation": "无法确认",
                "watch_indicators": [],
                "uncertainties": ["LLM不可用"],
                "non_advisory_note": "本分析仅为研究参考，不构成投资建议",
            })

    def _validate_schema(self, raw_output: str) -> Optional[Dict[str, Any]]:
        """校验 LLM 输出是否符合17字段 schema"""
        text = raw_output.strip()

        # 提取 JSON（支持 markdown code block）
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"JSON parse failed: {text[:200]}")
            return None

        if not isinstance(parsed, dict):
            return None

        # 检查必填字段
        missing = [f for f in ANALYSIS_SCHEMA_FIELDS if f not in parsed]
        if missing:
            logger.warning(f"Missing fields: {missing}")
            # 如果缺失不超过3个，补默认值
            if len(missing) <= 3:
                defaults = self._get_defaults()
                for f in missing:
                    parsed[f] = defaults.get(f, "")
                return parsed
            return None

        return parsed

    def _get_defaults(self) -> Dict[str, Any]:
        return {
            "event_summary": "",
            "event_type": "其他",
            "impact_direction": "neutral",
            "impact_strength": 1,
            "time_horizon": "short",
            "affected_industries": [],
            "affected_concepts": [],
            "upstream_downstream_paths": [],
            "direct_symbols": [],
            "indirect_symbols": [],
            "portfolio_hits": [],
            "impact_paths": [],
            "evidence_strength": "weak",
            "market_confirmation": "",
            "watch_indicators": [],
            "uncertainties": [],
            "non_advisory_note": "本分析仅为研究参考，不构成投资建议",
        }

    def _rule_based_fallback(self, news_item: Dict[str, Any]) -> Dict[str, Any]:
        """规则降级分析"""
        title = news_item.get("title", "")
        sentiment = news_item.get("sentiment", "neutral")

        direction = "neutral"
        if sentiment == "positive":
            direction = "positive"
        elif sentiment == "negative":
            direction = "negative"

        return {
            "event_summary": title[:100] if title else "无法提取事件摘要",
            "event_type": "其他",
            "impact_direction": direction,
            "impact_strength": 2,
            "time_horizon": "short",
            "affected_industries": [],
            "affected_concepts": [],
            "upstream_downstream_paths": [],
            "direct_symbols": [news_item.get("symbol", news_item.get("stock_code", ""))],
            "indirect_symbols": [],
            "portfolio_hits": [],
            "impact_paths": ["规则降级分析，未使用AI"],
            "evidence_strength": "weak",
            "market_confirmation": "未确认",
            "watch_indicators": [],
            "uncertainties": ["规则降级，分析深度有限"],
            "non_advisory_note": "本分析仅为研究参考，不构成投资建议",
        }

    def _apply_compliance_filter(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """非交易建议安全过滤"""
        try:
            from app.services.personal_investment.terminology_filter import (
                TerminologyFilter,
            )
            for key, value in result.items():
                if isinstance(value, str):
                    result[key], _ = TerminologyFilter.filter_text(value)
                elif isinstance(value, list):
                    result[key] = [
                        TerminologyFilter.filter_text(v)[0] if isinstance(v, str) else v
                        for v in value
                    ]
        except Exception as e:
            logger.warning(f"Compliance filter failed (non-blocking): {e}")

        # 确保 non_advisory_note 始终存在
        if not result.get("non_advisory_note"):
            result["non_advisory_note"] = "本分析仅为研究参考，不构成投资建议"

        return result

    async def _persist(self, record: NewsAnalysisRecord):
        """持久化分析记录（同一 analysis_id 以最新内容覆盖）"""
        db = get_mongo_db()
        doc = record.to_doc()
        await db[self.COLLECTION].update_one(
            {"analysis_id": doc["analysis_id"]},
            {"$set": doc},
            upsert=True,
        )


# 模块级单例
_news_agent: Optional[NewsImpactAgentService] = None


async def get_news_impact_agent_service() -> NewsImpactAgentService:
    global _news_agent
    if _news_agent is None:
        _news_agent = NewsImpactAgentService()
        await _news_agent.initialize()
    return _news_agent

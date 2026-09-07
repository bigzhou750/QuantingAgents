"""
LLM-as-Judge 评分器

使用大语言模型作为裁判，根据可配置的 rubric 对 trial 输出进行多维度评分。
支持自定义 judge model、rubric、prompt 模板和 JSON schema。

对应 spec 二期任务 2.1。
"""

import json
import logging
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource, ScoreStatus
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)

# 默认金融质量 rubric（对应任务 2.2）
DEFAULT_FINANCIAL_RUBRIC = {
    "dimensions": [
        {
            "name": "factual_consistency",
            "label": "事实一致性",
            "description": "输出中的事实陈述是否与已知数据和输入信息一致，无捏造或矛盾",
            "weight": 0.25,
        },
        {
            "name": "data_timeliness",
            "label": "数据时效性",
            "description": "引用的数据是否足够新鲜，是否标注了数据时间范围",
            "weight": 0.15,
        },
        {
            "name": "financial_reasoning",
            "label": "金融推理",
            "description": "分析逻辑是否严谨，因果关系是否成立，是否存在过度推断",
            "weight": 0.25,
        },
        {
            "name": "risk_disclosure",
            "label": "风险披露",
            "description": "是否充分提示了投资风险、不确定性和局限性",
            "weight": 0.20,
        },
        {
            "name": "conclusion_conservatism",
            "label": "结论保守性",
            "description": "结论是否适度保守，避免过度自信或绝对化表述",
            "weight": 0.15,
        },
    ]
}

DEFAULT_JUDGE_PROMPT_TEMPLATE = """你是一个专业的金融内容质量评审专家。请根据以下评分维度对 Agent 的输出进行评分。

## 用户输入
{input_text}

## Agent 输出
{output_text}

## 证据上下文
{evidence_text}

## 参考答案 / 期望输出
{expected_output_text}

## 数据窗口
{data_window_text}

## 评分维度
{rubric_text}

## 要求
请以 JSON 格式返回评分结果，格式如下：
{{
  "dimensions": [
    {{
      "name": "维度名称",
      "score": 0.0-1.0,
      "reason": "评分理由（简要说明）"
    }}
  ],
  "overall_score": 0.0-1.0,
  "overall_reason": "总体评价"
}}

仅返回 JSON，不要包含其他文字。"""


class JudgeContextBuilder:
    """把评测运行中的证据、参考答案和数据窗口组装成 Judge 上下文。"""

    @staticmethod
    def build(
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]],
        trial_data: Dict[str, Any],
    ) -> Dict[str, str]:
        case_snapshot = trial_data.get("case_snapshot") or {}
        expected_output = (case_config or {}).get("expected_output") or case_snapshot.get("expected_output")
        data_window = (case_config or {}).get("data_window") or (case_config or {}).get("data_window")

        evidence_lines = []
        for event in trace_events or []:
            if event.get("event_type") not in ("evidence", "retrieval", "citation"):
                continue
            data = event.get("data", {})
            snippet = data.get("snippet") or data.get("content") or data.get("text") or ""
            source = data.get("source") or data.get("provider") or event.get("event_id", "")
            if snippet:
                evidence_lines.append(f"- 来源: {source}\n  内容: {str(snippet)[:500]}")

        expected_lines = []
        if expected_output:
            if isinstance(expected_output, dict):
                expected_lines.append(
                    json.dumps(expected_output, ensure_ascii=False, indent=2)[:1000]
                )
            else:
                expected_lines.append(str(expected_output)[:1000])

        return {
            "evidence_text": "\n".join(evidence_lines) or "无可用证据上下文",
            "expected_output_text": "\n".join(expected_lines) or "未提供参考答案/期望输出",
            "data_window_text": (
                json.dumps(data_window, ensure_ascii=False)
                if data_window
                else "未提供数据窗口"
            ),
        }


class LLMJudgeScorer(BaseScorer):
    """LLM-as-Judge 评分器"""

    def __init__(
        self,
        judge_model: str = "qwen-plus",
        rubric: Optional[Dict[str, Any]] = None,
        prompt_template: Optional[str] = None,
        version: str = "1.0.0",
    ):
        self._judge_model = judge_model
        self._rubric = rubric or DEFAULT_FINANCIAL_RUBRIC
        self._prompt_template = prompt_template or DEFAULT_JUDGE_PROMPT_TEMPLATE
        self._version = version

    @property
    def name(self) -> str:
        return "llm_judge"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.LLM_JUDGE

    @property
    def version(self) -> str:
        return self._version

    @property
    def is_available(self) -> bool:
        """Judge 依赖不是可选 mock，缺失时必须失败关闭。"""
        try:
            import dashscope  # noqa: F401
            return True
        except ImportError:
            return False

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        """执行 LLM Judge 评分"""
        input_data = trial_data.get("input_data", {})
        output_data = trial_data.get("output_data", {})

        input_text = input_data.get("prompt", json.dumps(input_data, ensure_ascii=False))
        output_text = output_data.get("content", "") if isinstance(output_data, dict) else str(output_data)

        if not output_text:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="Agent 输出为空，无法评分",
                confidence=0.0,
                source=self.source,
                version=self.version,
                status=ScoreStatus.UNSCORABLE,
            )

        context = JudgeContextBuilder.build(trace_events, case_config, trial_data)
        if context["evidence_text"] == "无可用证据上下文" and context["expected_output_text"] == "未提供参考答案/期望输出":
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="缺少证据或参考答案，无法进行事实性评审，标记为不可评分",
                confidence=0.0,
                source=self.source,
                version=self.version,
                status=ScoreStatus.UNSCORABLE,
            )

        # 构建 rubric 文本
        rubric_text = self._format_rubric()

        if not self.is_available:
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason="dashscope SDK 未安装，LLM Judge 不可用",
                confidence=0.0,
                source=self.source,
                version=self.version,
                status=ScoreStatus.NOT_CONFIGURED,
            )

        # 构建 prompt
        prompt = self._prompt_template.format(
            input_text=input_text[:3000],
            output_text=output_text[:5000],
            evidence_text=context["evidence_text"][:2000],
            expected_output_text=context["expected_output_text"][:1000],
            data_window_text=context["data_window_text"][:500],
            rubric_text=rubric_text,
        )

        # 调用 LLM
        try:
            judge_output = await self._call_judge(prompt)
            parsed = self._parse_judge_output(judge_output)

            overall_score = parsed.get("overall_score", 0.0)
            overall_reason = parsed.get("overall_reason", "")

            return ScoreResult(
                score_name=self.name,
                score=max(0.0, min(1.0, overall_score)),
                passed=overall_score >= 0.6,
                reason=overall_reason,
                confidence=0.75 if context["evidence_text"] != "无可用证据上下文" else 0.5,
                source=self.source,
                version=self.version,
                raw_output={
                    "judge_model": self._judge_model,
                    "raw_response": judge_output,
                    "parsed": parsed,
                    "rubric_version": self._version,
                    "prompt_preview": prompt[:2000],
                    "has_evidence": context["evidence_text"] != "无可用证据上下文",
                    "has_expected_output": context["expected_output_text"] != "未提供参考答案/期望输出",
                },
            )
        except Exception as e:
            logger.error(f"LLM Judge scoring failed: {e}")
            return ScoreResult(
                score_name=self.name,
                score=0.0,
                passed=False,
                reason=f"LLM Judge 调用失败: {str(e)}",
                confidence=0.0,
                source=self.source,
                version=self.version,
                status=ScoreStatus.ERROR,
            )

    def _format_rubric(self) -> str:
        """格式化 rubric 为文本"""
        lines = []
        for dim in self._rubric.get("dimensions", []):
            lines.append(f"- **{dim['label']}** (权重 {dim['weight']:.0%}): {dim['description']}")
        return "\n".join(lines)

    async def _call_judge(self, prompt: str) -> str:
        """调用 judge LLM"""
        try:
            from dashscope import Generation

            response = Generation.call(
                model=self._judge_model,
                messages=[{"role": "user", "content": prompt}],
                result_format="message",
                temperature=0.1,
            )

            if response.status_code == 200:
                return response.output.choices[0].message.content
            else:
                raise RuntimeError(f"DashScope API error: {response.code} - {response.message}")

        except ImportError:
            raise RuntimeError("dashscope SDK not available, judge scoring is not configured")

    def _parse_judge_output(self, raw_output: str) -> Dict[str, Any]:
        """解析 judge 输出的 JSON"""
        # 尝试从 markdown code block 中提取 JSON
        text = raw_output.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse judge output as JSON: {text[:200]}")
            return {
                "dimensions": [],
                "overall_score": 0.0,
                "overall_reason": f"JSON 解析失败: {text[:200]}",
            }

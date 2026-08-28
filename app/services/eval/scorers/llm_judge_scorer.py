"""
LLM-as-Judge 评分器

使用大语言模型作为裁判，根据可配置的 rubric 对 trial 输出进行多维度评分。
支持自定义 judge model、rubric、prompt 模板和 JSON schema。

对应 spec 二期任务 2.1。
"""

import json
import logging
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource
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
                confidence=1.0,
                source=self.source,
                version=self.version,
            )

        # 构建 rubric 文本
        rubric_text = self._format_rubric()

        # 构建 prompt
        prompt = self._prompt_template.format(
            input_text=input_text[:3000],
            output_text=output_text[:5000],
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
                confidence=0.85,
                source=self.source,
                version=self.version,
                raw_output={
                    "judge_model": self._judge_model,
                    "raw_response": judge_output,
                    "parsed": parsed,
                    "rubric_version": self._version,
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
            logger.warning("dashscope not available, returning mock judge output")
            return json.dumps({
                "dimensions": [
                    {"name": d["name"], "score": 0.5, "reason": "mock: dashscope unavailable"}
                    for d in self._rubric.get("dimensions", [])
                ],
                "overall_score": 0.5,
                "overall_reason": "mock: dashscope SDK not installed",
            })

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

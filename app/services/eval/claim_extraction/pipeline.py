"""Claim 抽取流水线实现。

阶段顺序：归一化 -> 候选片段生成 -> 片段合并与完整性检查 -> Markdown/格式过滤
-> Claim 候选排序 -> 数量上限 -> ClaimEvidence 构造。
"""

import re
import uuid
from typing import Dict, List, Optional, Tuple

from app.models.eval import ClaimEvidence, ClaimVerdict
from app.services.eval.claim_extraction.models import (
    ClaimExtractionResult,
    ExcludedFragment,
)

MAX_CLAIMS = 20

TERMINAL_PUNCT = set("。！？!?")
FACTUAL_PREDICATES = (
    "是",
    "为",
    "达到",
    "上涨",
    "下降",
    "同比",
    "位于",
    "来自",
    "增长",
    "下滑",
    "超过",
    "低于",
)


def normalize_text(text: str) -> Tuple[str, List[int]]:
    """归一化 CRLF、Unicode 空白和连续空白，并保留到原文的映射。"""
    source_map: List[int] = []
    normalized: List[str] = []
    last_was_space = False
    index = 0
    while index < len(text):
        ch = text[index]
        if ch == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
            index += 1
            continue
        if ch.isspace():
            if not last_was_space:
                normalized.append("\n" if ch == "\n" else " ")
                source_map.append(index)
            last_was_space = True
        else:
            normalized.append(ch)
            source_map.append(index)
            last_was_space = False
        index += 1
    return "".join(normalized), source_map


def _line_spans(text: str) -> List[Tuple[str, int, int]]:
    """返回每行文本及 [start, end) 区间，end 不包含换行符。"""
    lines: List[Tuple[str, int, int]] = []
    start = 0
    for index, ch in enumerate(text):
        if ch == "\n":
            lines.append((text[start:index], start, index))
            start = index + 1
    if start < len(text):
        lines.append((text[start:], start, len(text)))
    return lines


def _needs_continuation(left: str, right: str) -> bool:
    """判断左右两个片段是否可能是同一事实被换行拆开。"""
    left = left.rstrip()
    right = right.lstrip()
    if not left or not right:
        return False
    if left.endswith(("(", "（", "[")):
        return True
    if re.search(r"(?i)\d{6}$", left) and re.match(r"(?i)(?:SH|SZ|BJ|SS|HK)\b", right):
        return True
    if re.search(r"(?i)\b(?:EPS|SH|SZ|BJ|PE|PB|ROE|ROA)\b$", left) and right[0].isalnum():
        return True
    # 数值换行通常不能无条件拼接，但仍作为一个待确认候选保留原文。
    if re.search(r"\d$", left) and re.match(r"\d+(?:\.\d+)?\s*(?:元|万|亿|%|％|倍)?", right):
        return True
    if re.search(r"(?:\d{4}年)$", left) and re.match(r"\d{1,2}月", right):
        return True
    return False


def _split_candidates(text: str) -> List[Dict[str, object]]:
    """按行和句末标点生成候选，保留原始 span。"""
    lines = _line_spans(text)
    candidates: List[Dict[str, object]] = []
    index = 0
    while index < len(lines):
        line_text, line_start, line_end = lines[index]
        merged_text = line_text
        merged_end = line_end
        while index + 1 < len(lines) and _needs_continuation(merged_text, lines[index + 1][0]):
            next_text, _next_start, next_end = lines[index + 1]
            merged_text = merged_text.rstrip() + " " + next_text.lstrip()
            merged_end = next_end
            index += 1
        for part_text, part_start, part_end in _split_sentence_spans(merged_text):
            candidates.append(
                {
                    "text": part_text,
                    "source_start": line_start + part_start,
                    "source_end": line_start + part_end,
                }
            )
        index += 1
    return candidates


def _split_sentence_spans(text: str) -> List[Tuple[str, int, int]]:
    """把一段文本按句末标点切分，标点保留在片段末尾。"""
    parts: List[Tuple[str, int, int]] = []
    part_start = 0
    index = 0
    while index < len(text):
        if text[index] in TERMINAL_PUNCT:
            part_text = text[part_start : index + 1].strip()
            if part_text:
                parts.append((part_text, part_start, index + 1))
            part_start = index + 1
        index += 1
    tail = text[part_start:].strip()
    if tail:
        tail_start = part_start + (len(text[part_start:]) - len(text[part_start:].lstrip()))
        parts.append((tail, tail_start, len(text)))
    return parts


def _clean_inline_format(text: str) -> str:
    """去掉常见 Markdown 行内格式，便于判断是否为纯标签。"""
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    cleaned = re.sub(r"`(.+?)`", r"\1", cleaned)
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned)
    cleaned = re.sub(r"^\s*>\s*", "", cleaned)
    return cleaned.strip()


def _is_table_separator(text: str) -> bool:
    return bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", text))


def _classify_candidate(text: str, next_text: str = "") -> Optional[str]:
    """返回排除原因；正常候选返回 None。"""
    stripped = text.strip()
    if not stripped:
        return "empty"
    if stripped.startswith("#"):
        return "markdown_heading"
    if stripped.startswith("```") or stripped.startswith("~~~"):
        return "code_fence"
    if stripped.startswith(">"):
        return "quote_block"
    if _is_table_separator(stripped):
        return "table_separator"
    if re.match(r"^[-*_]{3,}\s*$", stripped):
        return "horizontal_rule"
    if "|" in stripped and _is_table_separator(next_text):
        return "table_header"

    cleaned = _clean_inline_format(stripped)
    if len(cleaned) < 8:
        return "format_fragment"
    has_punct = any(ch in TERMINAL_PUNCT for ch in cleaned)
    has_fact = bool(re.search(r"\d", cleaned)) or any(
        predicate in cleaned for predicate in FACTUAL_PREDICATES
    )
    if not has_punct and not has_fact and len(cleaned) <= 12:
        return "format_fragment"
    return None


def _strip_markdown_surface(text: str) -> str:
    """去掉列表标记、引用前缀和行内加粗，保留完整事实文本。"""
    stripped = text.strip()
    stripped = re.sub(r"^\s*[-*+]\s+", "", stripped)
    stripped = re.sub(r"^\s*>\s*", "", stripped)
    stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
    return stripped.strip()


def _filter_candidates(
    candidates: List[Dict[str, object]],
) -> Tuple[List[Dict[str, object]], List[ExcludedFragment]]:
    """过滤 Markdown 和格式片段，返回有效候选与排除记录。"""
    valid: List[Dict[str, object]] = []
    excluded: List[ExcludedFragment] = []
    in_code_block = False
    for index, candidate in enumerate(candidates):
        raw_text = str(candidate["text"])
        stripped = raw_text.strip()
        next_text = str(candidates[index + 1]["text"]).strip() if index + 1 < len(candidates) else ""
        reason = _classify_candidate(raw_text, next_text)
        if reason == "code_fence":
            in_code_block = not in_code_block
            excluded.append(
                ExcludedFragment(
                    text=stripped,
                    reason="code_fence",
                    source_start=candidate.get("source_start"),
                    source_end=candidate.get("source_end"),
                )
            )
            continue
        if in_code_block:
            excluded.append(
                ExcludedFragment(
                    text=stripped,
                    reason="code_block",
                    source_start=candidate.get("source_start"),
                    source_end=candidate.get("source_end"),
                )
            )
            continue
        if reason:
            excluded.append(
                ExcludedFragment(
                    text=stripped,
                    reason=reason,
                    source_start=candidate.get("source_start"),
                    source_end=candidate.get("source_end"),
                )
            )
            continue
        cleaned = _strip_markdown_surface(raw_text)
        if len(cleaned) < 8:
            excluded.append(
                ExcludedFragment(
                    text=stripped,
                    reason="too_short",
                    source_start=candidate.get("source_start"),
                    source_end=candidate.get("source_end"),
                )
            )
            continue
        candidate["text"] = cleaned
        valid.append(candidate)
    return valid, excluded


def _rank_candidate(candidate: Dict[str, object]) -> float:
    """对候选做事实质量排序，残缺和不确定片段排后。"""
    text = str(candidate["text"])
    score = 0.0
    if any(ch in TERMINAL_PUNCT for ch in text):
        score += 4.0
    if re.search(r"\d", text):
        score += 3.0
    if any(predicate in text for predicate in FACTUAL_PREDICATES):
        score += 2.0
    if len(text) >= 12:
        score += 1.0
    if not any(ch in TERMINAL_PUNCT for ch in text):
        score -= 1.5
    if re.search(r"\d+\s+\d+\s*(?:元|万|亿|%|％|倍)?$", text):
        score -= 2.0
    return score


def extract_claims(
    output_text: str,
    max_claims: int = MAX_CLAIMS,
) -> ClaimExtractionResult:
    """从原始输出中抽取结构化 Claim。"""
    if not output_text:
        return ClaimExtractionResult()

    normalized_text, _source_map = normalize_text(output_text)
    candidates = _split_candidates(normalized_text)
    valid, excluded = _filter_candidates(candidates)
    candidate_count = len(candidates)

    ranked = sorted(
        enumerate(valid),
        key=lambda item: (-_rank_candidate(item[1]), item[0]),
    )
    ranked = [candidate for _index, candidate in ranked]

    truncated = len(ranked) > max_claims
    truncated_count = max(0, len(ranked) - max_claims)
    truncated_at = ranked[max_claims]["source_start"] if truncated else None
    selected = ranked[:max_claims]
    claims = [
        ClaimEvidence(
            claim_id=f"claim_{uuid.uuid4().hex[:8]}",
            claim_text=str(candidate["text"]),
            verdict=ClaimVerdict.UNSUPPORTED,
            confidence=0.0,
            reason="待证据映射",
            source_start=candidate.get("source_start"),
            source_end=candidate.get("source_end"),
        )
        for candidate in selected
    ]

    return ClaimExtractionResult(
        claims=claims,
        candidate_count=candidate_count,
        claim_count=len(claims),
        claim_truncated=truncated,
        claim_truncated_count=truncated_count,
        claim_truncated_at=truncated_at,
        excluded=excluded,
        normalized_text=normalized_text,
    )

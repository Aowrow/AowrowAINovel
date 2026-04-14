from __future__ import annotations

import re
from typing import Any


DEFAULT_ANTI_AI_STYLE_POLICY: dict[str, Any] = {
    "enabled": True,
    "strict_level": "high",
    "banned_phrases": [
        "总之",
        "综上所述",
        "需要注意的是",
        "首先",
        "其次",
        "最后",
        "接上回",
        "书接上文",
        "作为一个",
    ],
    "max_connector_density": 0.018,
    "max_repeated_opening_ratio": 0.25,
}


def normalize_policy(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_ANTI_AI_STYLE_POLICY)
    out.update(dict(raw or {}))
    out["enabled"] = bool(out.get("enabled", True))
    out["strict_level"] = str(out.get("strict_level", "high")).strip() or "high"
    phrases = out.get("banned_phrases", DEFAULT_ANTI_AI_STYLE_POLICY["banned_phrases"])
    if not isinstance(phrases, list):
        phrases = list(DEFAULT_ANTI_AI_STYLE_POLICY["banned_phrases"])
    out["banned_phrases"] = [str(x).strip() for x in phrases if str(x).strip()]
    out["max_connector_density"] = float(out.get("max_connector_density", 0.018))
    out["max_repeated_opening_ratio"] = float(out.get("max_repeated_opening_ratio", 0.25))
    return out


def render_generation_constraints(raw_policy: dict[str, Any] | None) -> str:
    cfg = normalize_policy(raw_policy)
    if not cfg["enabled"]:
        return ""
    banned = "、".join(cfg["banned_phrases"])
    return (
        "【Anti-AI-Style】\n"
        f"1) 禁止套话/总结腔：{banned}\n"
        "2) 禁止段落机械连接（首先/其次/最后式列点推进）。\n"
        "3) 开篇不得复述上一章同一段环境或心理独白。\n"
        "4) 用动作、对话、细节推动情绪，不要抽象概括情绪。\n"
    )


def detect_style_issues(text: str, raw_policy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = normalize_policy(raw_policy)
    if not cfg["enabled"]:
        return []
    issues: list[dict[str, Any]] = []
    body = text or ""

    phrase_hits = []
    for phrase in cfg["banned_phrases"]:
        count = body.count(phrase)
        if count > 0:
            phrase_hits.append({"phrase": phrase, "count": count})
    if phrase_hits:
        issues.append(
            {
                "rule_id": "ST_BANNED_PHRASES",
                "severity": "error",
                "detail": f"Banned style phrases found: {phrase_hits}",
            },
        )

    connector_tokens = ["首先", "其次", "最后", "同时", "然而", "因此", "总之", "综上所述"]
    token_hits = sum(body.count(tok) for tok in connector_tokens)
    char_count = max(1, len(body))
    density = token_hits / char_count
    if density > float(cfg["max_connector_density"]):
        issues.append(
            {
                "rule_id": "ST_CONNECTOR_DENSITY",
                "severity": "warn",
                "detail": f"Connector density too high: {density:.4f}",
            },
        )

    lines = [x.strip() for x in body.splitlines() if x.strip()]
    opening_units = [_first_clause(line) for line in lines if len(line) >= 8]
    if opening_units:
        duplicated = len(opening_units) - len(set(opening_units))
        ratio = duplicated / len(opening_units)
        if ratio > float(cfg["max_repeated_opening_ratio"]):
            issues.append(
                {
                    "rule_id": "ST_REPEATED_OPENING",
                    "severity": "warn",
                    "detail": f"Repeated opening ratio too high: {ratio:.2f}",
                },
            )
    return issues


def rewrite_style_issues(text: str, raw_policy: dict[str, Any] | None = None) -> str:
    cfg = normalize_policy(raw_policy)
    out = text
    for phrase in cfg["banned_phrases"]:
        if phrase in out:
            out = out.replace(phrase, "")
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def _first_clause(line: str) -> str:
    m = re.split(r"[，。！？；:：]", line, maxsplit=1)
    return m[0].strip() if m else line.strip()


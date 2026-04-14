from __future__ import annotations

import re
from typing import Any

from .anti_ai_style import detect_style_issues


NEGATIVE_TOKENS = ["愤怒", "恐惧", "紧张", "绝望", "仇恨", "压迫", "威胁", "焦虑"]
POSITIVE_TOKENS = ["释然", "信任", "温暖", "希望", "坚定", "勇气", "喜悦", "认可"]


def analyze_chapter(
    chapter_no: int,
    draft_markdown: str,
    chapter_summary: str,
    story_bible: dict[str, Any],
    runtime_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = _strip_markdown_scaffold(draft_markdown)
    runtime_state = runtime_state or {}
    style_issues = detect_style_issues(text)
    hooks = _extract_hooks(text)
    foreshadows = _extract_foreshadows(text, chapter_no)
    emotional_arc = _estimate_emotion(text)
    character_states = _extract_character_states(text, story_bible, runtime_state, emotional_arc)
    plot_points = _extract_plot_points(text)
    conflict = _estimate_conflict(text, emotional_arc)
    continuation_signals = _build_continuation_signals(text, chapter_summary)
    progress_signals = _build_progress_signals(text, chapter_summary, runtime_state)
    foreshadow_updates = _summarize_foreshadow_updates(foreshadows)
    ending_shape = _build_ending_shape(text)
    repetition_markers = _build_repetition_markers(text)

    scores = _score_quality(
        text=text,
        style_issues=style_issues,
        conflict_level=int(conflict.get("level", 5)),
        hook_count=len(hooks),
    )
    suggestions = _build_suggestions(style_issues=style_issues, scores=scores)

    return {
        "plot_stage": "发展",
        "summary": chapter_summary,
        "hooks": hooks,
        "foreshadows": foreshadows,
        "conflict": conflict,
        "emotional_arc": emotional_arc,
        "character_states": character_states,
        "organization_states": [],
        "plot_points": plot_points,
        "continuation_signals": continuation_signals,
        "progress_signals": progress_signals,
        "thread_updates": {"advanced": progress_signals.get("touched_threads", [])},
        "foreshadow_updates": foreshadow_updates,
        "ending_shape": ending_shape,
        "repetition_markers": repetition_markers,
        "scenes": _extract_scenes(text),
        "pacing": _estimate_pacing(text),
        "scores": scores,
        "suggestions": suggestions,
        "dialogue_ratio": _dialogue_ratio(text),
        "description_ratio": _description_ratio(text),
        "style_issues": style_issues,
    }


def _strip_markdown_scaffold(draft_markdown: str) -> str:
    lines = []
    skip = False
    for line in (draft_markdown or "").splitlines():
        s = line.strip()
        if s.startswith("## 本章模板对齐点") or s.startswith("## Template Alignment"):
            skip = True
            continue
        if skip and s.startswith("## "):
            skip = False
        if skip:
            continue
        if s.startswith("# "):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_hooks(text: str) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    candidates = re.findall(r"[^。！？\n]{8,40}[？!?]", text)
    for idx, frag in enumerate(candidates[:4], start=1):
        hooks.append(
            {
                "type": "悬念",
                "content": frag.strip(),
                "strength": min(10, 6 + idx),
                "position": "中段",
                "keyword": frag.strip()[:25],
            },
        )
    return hooks


def _extract_foreshadows(text: str, chapter_no: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    planted_marks = ["线索", "异样", "谜团", "不对劲", "秘密"]
    resolved_marks = ["真相", "揭开", "终于明白", "回想起", "证实"]
    snippet = _pick_keyword_snippet(text)
    if any(tok in text for tok in planted_marks):
        items.append(
            {
                "title": f"第{chapter_no}章线索",
                "content": snippet or "章节埋入了一条潜在线索",
                "type": "planted",
                "strength": 7,
                "subtlety": 7,
                "reference_chapter": None,
                "reference_foreshadow_id": None,
                "keyword": snippet[:25] if snippet else "线索浮现",
                "category": "mystery",
                "is_long_term": True,
                "related_characters": [],
                "estimated_resolve_chapter": chapter_no + 3,
            },
        )
    if any(tok in text for tok in resolved_marks):
        items.append(
            {
                "title": f"第{chapter_no}章回收点",
                "content": snippet or "章节回收了一个前置线索",
                "type": "resolved",
                "strength": 7,
                "subtlety": 5,
                "reference_chapter": max(1, chapter_no - 2),
                "reference_foreshadow_id": None,
                "keyword": snippet[:25] if snippet else "真相揭开",
                "category": "event",
                "is_long_term": False,
                "related_characters": [],
                "estimated_resolve_chapter": chapter_no,
            },
        )
    return items


def _extract_character_states(
    text: str,
    story_bible: dict[str, Any],
    runtime_state: dict[str, Any],
    emotional_arc: dict[str, Any],
) -> list[dict[str, Any]]:
    chars = story_bible.get("characters", []) if isinstance(story_bible, dict) else []
    runtime_states = {
        str(item.get("name", "")): item
        for item in runtime_state.get("character_states", [])
        if isinstance(item, dict)
    }
    out: list[dict[str, Any]] = []
    for item in chars:
        name = str(item.get("name", "")).strip()
        if not name or name not in text:
            continue
        before = str(runtime_states.get(name, {}).get("state", runtime_states.get(name, {}).get("note", ""))).strip() or "未知"
        after = _emotion_to_state(str(emotional_arc.get("primary_emotion", "紧绷")))
        out.append(
            {
                "character_name": name,
                "state_before": before,
                "state_after": after,
                "psychological_change": f"{before}→{after}",
                "relationship_changes": {},
                "organization_changes": [],
            },
        )
    return out


def _extract_plot_points(text: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    sentences = [s.strip() for s in re.split(r"[。！？\n]+", text) if s.strip()]
    for idx, sent in enumerate(sentences[:5], start=1):
        points.append(
            {
                "content": sent[:80],
                "type": "transition" if idx < 3 else "conflict",
                "importance": max(0.5, 1 - idx * 0.1),
                "impact": "推进章节目标",
                "keyword": sent[:25],
            },
        )
    return points


def _build_continuation_signals(text: str, chapter_summary: str) -> dict[str, Any]:
    combined = f"{text}\n{chapter_summary}"
    carry_forward_elements: list[str] = []
    for token in ["石门", "祭坛", "火光", "异响", "线索", "秘密", "遗迹", "甬道"]:
        if token in combined and token not in carry_forward_elements:
            carry_forward_elements.append(token)
    return {
        "carry_forward_elements": carry_forward_elements,
        "has_open_loop": any(token in combined for token in ["异响", "线索", "秘密", "谜团", "不对劲"]),
    }


def _build_progress_signals(text: str, chapter_summary: str, runtime_state: dict[str, Any]) -> dict[str, Any]:
    combined = f"{text}\n{chapter_summary}"
    objective_hit = any(token in combined for token in ["确认", "推进", "发现", "逼近", "兑现", "明白", "决定"])
    touched_threads: list[str] = []
    for item in runtime_state.get("active_threads", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        match_terms = _thread_match_terms(title)
        matched_terms = _matched_thread_terms(match_terms, combined)
        if title in combined or _is_thread_touched_by_terms(match_terms, matched_terms):
            touched_threads.append(title)
    return {
        "objective_status": "fulfilled" if objective_hit else "partial",
        "touched_threads": touched_threads,
    }


def _summarize_foreshadow_updates(foreshadows: list[dict[str, Any]]) -> dict[str, list[str]]:
    planted = [str(item.get("title", "")).strip() for item in foreshadows if item.get("type") == "planted"]
    resolved = [str(item.get("title", "")).strip() for item in foreshadows if item.get("type") == "resolved"]
    return {
        "planted": [item for item in planted if item],
        "resolved": [item for item in resolved if item],
    }


def _build_ending_shape(text: str) -> dict[str, Any]:
    ending_excerpt = _ending_excerpt(text)
    if any(token in ending_excerpt for token in ["真相", "终于确认", "突然亮起", "忽然明白", "发现"]):
        return {"type": "reveal", "evidence": ending_excerpt or "chapter ending introduces a reveal"}
    if any(token in ending_excerpt for token in ["忽然", "下一瞬", "门后传来", "骤然", "猛地"]):
        return {"type": "cliff", "evidence": ending_excerpt or "chapter ending leaves immediate threat"}
    return {"type": "transition", "evidence": ending_excerpt or "chapter ending mainly transitions forward"}


def _build_repetition_markers(text: str) -> dict[str, Any]:
    repeated_terms: list[str] = []
    for term in ["石门", "祭坛", "异响", "线索", "秘密", "遗迹", "火光"]:
        if text.count(term) >= 2:
            repeated_terms.append(term)
    return {
        "repeated_terms": repeated_terms,
        "has_heavy_repetition": bool(repeated_terms),
    }


def _estimate_conflict(text: str, emotional_arc: dict[str, Any]) -> dict[str, Any]:
    hit = sum(text.count(tok) for tok in ["冲突", "对抗", "反击", "威胁", "压力"])
    level = min(10, max(3, hit + int(emotional_arc.get("intensity", 5) // 2)))
    return {
        "types": ["人物冲突"] if level >= 6 else ["内心冲突"],
        "parties": [],
        "description": "章节冲突压力持续推进",
        "level": level,
        "progress": min(95, 35 + level * 5),
    }


def _estimate_emotion(text: str) -> dict[str, Any]:
    neg = sum(text.count(tok) for tok in NEGATIVE_TOKENS)
    pos = sum(text.count(tok) for tok in POSITIVE_TOKENS)
    if neg >= pos:
        primary = "紧张"
        intensity = min(10, 5 + neg)
    else:
        primary = "坚定"
        intensity = min(10, 5 + pos)
    return {
        "primary_emotion": primary,
        "intensity": max(1, intensity),
        "trajectory": "上扬" if pos > neg else "压迫",
    }


def _score_quality(text: str, style_issues: list[dict[str, Any]], conflict_level: int, hook_count: int) -> dict[str, float]:
    base = 6.5
    penalty = sum(0.6 if i.get("severity") == "error" else 0.3 for i in style_issues)
    pacing = max(1.0, min(10.0, base + (conflict_level - 5) * 0.3 - penalty))
    engagement = max(1.0, min(10.0, base + hook_count * 0.4 - penalty * 0.7))
    coherence = max(1.0, min(10.0, base - penalty * 0.8))
    overall = round((pacing + engagement + coherence) / 3.0, 1)
    return {
        "pacing": round(pacing, 1),
        "engagement": round(engagement, 1),
        "coherence": round(coherence, 1),
        "overall": overall,
    }


def _build_suggestions(style_issues: list[dict[str, Any]], scores: dict[str, float]) -> list[str]:
    out: list[str] = []
    for issue in style_issues[:3]:
        rid = str(issue.get("rule_id", "STYLE"))
        out.append(f"【文风问题】{rid}: {issue.get('detail', '')}")
    overall = float(scores.get("overall", 0.0))
    if overall < 6.0:
        out.append("【节奏问题】减少解释句，改用动作推进和冲突反馈。")
        out.append("【情绪问题】增加角色可感知动作与生理反应。")
    elif overall < 8.0:
        out.append("【优化建议】保持剧情推进，减少段首模板句。")
    return out[:5]


def _extract_scenes(text: str) -> list[str]:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return [p[:80] for p in paras[:4]]


def _estimate_pacing(text: str) -> str:
    n = len(text)
    if n < 1800:
        return "快"
    if n > 4200:
        return "慢"
    return "中"


def _dialogue_ratio(text: str) -> float:
    if not text:
        return 0.0
    quote_count = text.count("“") + text.count("\"")
    return round(min(1.0, quote_count / max(1, len(text) / 80)), 3)


def _description_ratio(text: str) -> float:
    if not text:
        return 0.0
    marks = sum(text.count(tok) for tok in ["看见", "听见", "闻到", "空气", "光线", "脚步"])
    return round(min(1.0, marks / max(1, len(text) / 120)), 3)


def _emotion_to_state(primary_emotion: str) -> str:
    mapping = {
        "紧张": "戒备与压迫感并存",
        "坚定": "目标明确，决策趋于果断",
    }
    return mapping.get(primary_emotion, "情绪波动中保持行动")


def _pick_keyword_snippet(text: str) -> str:
    parts = [p.strip() for p in re.split(r"[。！？\n]+", text) if 8 <= len(p.strip()) <= 40]
    return parts[0] if parts else ""


def _ending_excerpt(text: str) -> str:
    sentences = [s.strip() for s in re.split(r"[。！？\n]+", text) if s.strip()]
    return sentences[-1] if sentences else ""


def _thread_match_terms(title: str) -> list[str]:
    cleaned = "".join(re.findall(r"[\u4e00-\u9fff]+", title))
    terms: list[str] = []
    salient_candidates = [
        "地下遗迹",
        "石门",
        "异响",
        "线索",
        "秘密",
        "祭坛",
        "火光",
        "甬道",
        "真相",
        "苏醒",
    ]
    for candidate in salient_candidates:
        if candidate in cleaned and candidate not in terms:
            terms.append(candidate)
    if not terms and len(cleaned) >= 4:
        terms.append(cleaned)
    return terms


def _is_thread_touched_by_terms(match_terms: list[str], matched_terms: list[str]) -> bool:
    if not matched_terms:
        return False
    if any(len(term) >= 4 for term in matched_terms):
        return True
    return len({term for term in matched_terms if len(term) >= 2}) >= 2 and len(match_terms) >= 2


def _matched_thread_terms(match_terms: list[str], combined: str) -> list[str]:
    synonyms = {
        "异响": ["异响", "回响", "响动", "震动"],
        "苏醒": ["苏醒", "醒来", "复苏"],
        "线索": ["线索", "痕迹", "端倪"],
        "秘密": ["秘密", "真相"],
    }
    matched: list[str] = []
    for term in match_terms:
        candidates = synonyms.get(term, [term])
        if any(candidate in combined for candidate in candidates):
            matched.append(term)
    return matched


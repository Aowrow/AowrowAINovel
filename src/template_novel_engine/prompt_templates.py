from __future__ import annotations

from .anti_ai_style import render_generation_constraints


DEFAULT_SYSTEM_PROMPT = """你是中文网文职业作者。
目标：使用“爆款模板结构”写“原创章节”，只模仿结构与节奏，不抄原文内容。
硬约束：
1) 主角必须保持主动决策。
2) 不得跳过阶段，不得提前消耗终局高潮。
3) 伏笔要可回收，线索推进要可追踪。
4) 不得输出占位词（TODO/TBD/待补/......）。
5) 输出必须是中文 Markdown。
"""


def chapter_generation_extra_constraints(anti_ai_style_cfg: dict | None) -> str:
    return render_generation_constraints(anti_ai_style_cfg)


def build_chapter_prompt_payload(
    contract: dict,
    context_bundle: dict,
    precheck: dict,
    anti_ai_style_cfg: dict | None,
) -> dict[str, str]:
    continuation = context_bundle.get("continuation_anchor", {})
    recent_progress = context_bundle.get("recent_progress", {})
    warnings = precheck.get("warnings", []) if isinstance(precheck, dict) else []
    anti_repetition = recent_progress.get("anti_repetition", [])
    if not isinstance(anti_repetition, list):
        anti_repetition = []

    user_prompt = "\n".join(
        [
            "<task>",
            f"本章目标：{contract.get('chapter_objective', '')}",
            "</task>",
            "<continuation>",
            f"上一章摘要：{recent_progress.get('summary', '')}",
            f"上一章尾部：{continuation.get('tail', '')}",
            "</continuation>",
            "<anti_repetition>",
            *[str(item) for item in anti_repetition],
            "</anti_repetition>",
            "<precheck>",
            *[str(item) for item in warnings],
            "</precheck>",
            chapter_generation_extra_constraints(anti_ai_style_cfg),
        ]
    )
    return {"system_prompt": DEFAULT_SYSTEM_PROMPT, "user_prompt": user_prompt}


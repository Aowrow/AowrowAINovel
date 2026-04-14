from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from .markdown_utils import (
    MarkdownSection,
    clean_sentence,
    extract_backticks,
    extract_bullets,
    extract_numbered,
    first_nonempty_line,
    parse_sections,
)


STAGE_TITLE_RE = re.compile(r"(开篇钩子|第[一二三四五六七八九十0-9]+阶段|终局|结局)")
RHYTHM_RE = re.compile(r"(\d+)\s*(?:到|-|~|至)\s*(\d+)\s*集[:：]\s*(.+)")


def parse_template_markdown(markdown: str, source_file: str) -> dict[str, Any]:
    sections = parse_sections(markdown)
    formulas = extract_backticks(markdown)

    stages = _extract_stages(sections)
    rhythm_beats = _extract_rhythm(sections)
    dialogue_patterns = _extract_dialogue_patterns(sections)
    principles = _extract_principles(sections)
    motifs = _extract_reusable_motifs(sections)

    core_premise = formulas[0] if formulas else _guess_core_premise(sections)

    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": source_file,
        "core_premise": core_premise,
        "template_formulas": formulas,
        "narrative_stages": stages,
        "rhythm_beats": rhythm_beats,
        "dialogue_patterns": dialogue_patterns,
        "principles": principles,
        "reusable_motifs": motifs,
        "signals": {
            "stage_count": len(stages),
            "rhythm_count": len(rhythm_beats),
            "dialogue_pattern_count": len(dialogue_patterns),
            "principle_count": len(principles),
        },
    }


def _extract_stages(sections: list[MarkdownSection]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    counter = 1

    for sec in sections:
        if not STAGE_TITLE_RE.search(sec.title):
            continue
        if sec.level > 4:
            continue

        bullets = extract_bullets(sec.lines)
        numbered = extract_numbered(sec.lines)
        summary = first_nonempty_line(sec.lines)
        if not summary and bullets:
            summary = bullets[0]

        stage_id = f"stage_{counter:02d}"
        counter += 1

        stages.append(
            {
                "stage_id": stage_id,
                "title": clean_sentence(sec.title),
                "summary": summary,
                "key_points": bullets[:8],
                "actions": numbered[:8],
            },
        )

    return stages


def _extract_rhythm(sections: list[MarkdownSection]) -> list[dict[str, Any]]:
    beats: list[dict[str, Any]] = []

    for sec in sections:
        title = sec.title.lower()
        if "方法 3" not in title and "方法3" not in title and "每 8 到 10 集" not in sec.title:
            continue

        for raw in sec.lines:
            m = RHYTHM_RE.search(raw)
            if not m:
                continue
            beats.append(
                {
                    "chapter_start": int(m.group(1)),
                    "chapter_end": int(m.group(2)),
                    "objective": clean_sentence(m.group(3)),
                },
            )

    if beats:
        return beats

    # fallback: detect any global "x到y集"
    for sec in sections:
        for raw in sec.lines:
            m = RHYTHM_RE.search(raw)
            if not m:
                continue
            beats.append(
                {
                    "chapter_start": int(m.group(1)),
                    "chapter_end": int(m.group(2)),
                    "objective": clean_sentence(m.group(3)),
                },
            )
    return beats


def _extract_dialogue_patterns(sections: list[MarkdownSection]) -> list[dict[str, str]]:
    patterns: list[dict[str, str]] = []
    target_sections = [
        sec for sec in sections if ("方法 4" in sec.title or "方法4" in sec.title or "台词" in sec.title)
    ]

    for sec in target_sections:
        for bullet in extract_bullets(sec.lines):
            if "：" in bullet:
                name, desc = bullet.split("：", 1)
            elif ":" in bullet:
                name, desc = bullet.split(":", 1)
            else:
                continue
            patterns.append(
                {
                    "name": clean_sentence(name),
                    "description": clean_sentence(desc),
                },
            )
    return patterns


def _extract_principles(sections: list[MarkdownSection]) -> list[dict[str, str]]:
    principles: list[dict[str, str]] = []
    for sec in sections:
        if "原则" not in sec.title:
            continue
        summary = first_nonempty_line(sec.lines)
        principles.append(
            {
                "title": clean_sentence(sec.title),
                "detail": summary,
            },
        )
    return principles


def _extract_reusable_motifs(sections: list[MarkdownSection]) -> list[str]:
    motifs: list[str] = []
    for sec in sections:
        if "可复用" in sec.title or "母题" in sec.title:
            motifs.extend(extract_bullets(sec.lines))
            motifs.extend(extract_numbered(sec.lines))
    return [clean_sentence(m) for m in motifs if m]


def _guess_core_premise(sections: list[MarkdownSection]) -> str:
    for sec in sections:
        if "一句话概括" in sec.title or "概括" in sec.title:
            line = first_nonempty_line(sec.lines)
            if line:
                return line
    for sec in sections:
        line = first_nonempty_line(sec.lines)
        if line:
            return line
    return "Template premise not found."


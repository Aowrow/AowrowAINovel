from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .markdown_utils import (
    MarkdownSection,
    clean_sentence,
    extract_bullets,
    first_nonempty_line,
    parse_key_values,
    parse_markdown_table,
    parse_sections,
)


def build_story_bible(markdown: str, source_file: str) -> dict[str, Any]:
    sections = parse_sections(markdown)

    metadata = _extract_metadata(sections)
    premise = _extract_premise(sections)
    world = _extract_world(sections)
    characters = _extract_characters(sections)
    factions = _extract_factions(sections)
    conflicts = _extract_conflicts(sections)
    constraints = _extract_constraints(sections)

    if not characters:
        characters = [
            {
                "name": metadata.get("protagonist_name", "Protagonist"),
                "role": "protagonist",
                "goal": "Recover agency and complete the main arc.",
                "flaw": "Undefined",
                "arc": "From passive to active actor.",
            },
        ]

    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": source_file,
        "metadata": metadata,
        "premise": premise,
        "world": world,
        "characters": characters,
        "factions": factions,
        "conflicts": conflicts,
        "constraints": constraints,
    }


def _extract_metadata(sections: list[MarkdownSection]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Untitled Story",
        "genre": "unknown",
        "tone": "dramatic",
        "target_chapters": 40,
        "chapter_word_target": 3000,
    }
    for sec in sections:
        if "基本信息" not in sec.title and "metadata" not in sec.title.lower():
            continue
        kv = parse_key_values(sec.lines)
        data["title"] = kv.get("书名", kv.get("title", data["title"]))
        data["genre"] = kv.get("题材", kv.get("genre", data["genre"]))
        data["tone"] = kv.get("基调", kv.get("tone", data["tone"]))
        data["protagonist_name"] = kv.get("主角", kv.get("protagonist", "Protagonist"))

        if "目标章节" in kv:
            data["target_chapters"] = _to_int(kv["目标章节"], data["target_chapters"])
        if "target_chapters" in kv:
            data["target_chapters"] = _to_int(kv["target_chapters"], data["target_chapters"])
        if "章节字数" in kv:
            data["chapter_word_target"] = _to_int(kv["章节字数"], data["chapter_word_target"])
        if "chapter_word_target" in kv:
            data["chapter_word_target"] = _to_int(kv["chapter_word_target"], data["chapter_word_target"])

    return data


def _extract_premise(sections: list[MarkdownSection]) -> dict[str, Any]:
    premise: dict[str, Any] = {
        "logline": "",
        "theme": "",
        "selling_points": [],
    }
    for sec in sections:
        lowered = sec.title.lower()
        if "故事主旨" in sec.title or "故事梗概" in sec.title or "premise" in lowered:
            kv = parse_key_values(sec.lines)
            premise["logline"] = kv.get("一句话", kv.get("logline", first_nonempty_line(sec.lines)))
            premise["theme"] = kv.get("主题", kv.get("theme", ""))
            premise["selling_points"] = [_drop_label_prefix(item) for item in extract_bullets(sec.lines)[:8]]
            break
    return premise


def _extract_world(sections: list[MarkdownSection]) -> dict[str, Any]:
    world: dict[str, Any] = {
        "era": "",
        "locations": [],
        "rules": [],
        "power_system": "",
    }
    for sec in sections:
        lowered = sec.title.lower()
        if "世界观" not in sec.title and "world" not in lowered:
            continue
        kv = parse_key_values(sec.lines)
        world["era"] = kv.get("时代", kv.get("era", world["era"]))
        world["power_system"] = kv.get("力量体系", kv.get("power_system", world["power_system"]))
        world["locations"] = _split_values(kv.get("核心地点", kv.get("locations", "")))
        world["rules"] = extract_bullets(sec.lines)[:12]
        break
    return world


def _extract_characters(sections: list[MarkdownSection]) -> list[dict[str, str]]:
    for sec in sections:
        lowered = sec.title.lower()
        if "角色" not in sec.title and "character" not in lowered:
            continue

        table_records = parse_markdown_table(sec.lines)
        if table_records:
            return [
                {
                    "name": item.get("name", item.get("角色名", item.get("姓名", "Unknown"))),
                    "role": item.get("role", item.get("定位", "supporting")),
                    "goal": item.get("goal", item.get("目标", "")),
                    "flaw": item.get("flaw", item.get("缺陷", "")),
                    "arc": item.get("arc", item.get("弧光", "")),
                }
                for item in table_records
            ]

        # fallback: bullet lines like "Name - role - goal"
        characters: list[dict[str, str]] = []
        for bullet in extract_bullets(sec.lines):
            parts = [clean_sentence(p) for p in bullet.replace("：", "-").split("-") if clean_sentence(p)]
            if not parts:
                continue
            characters.append(
                {
                    "name": parts[0],
                    "role": parts[1] if len(parts) > 1 else "supporting",
                    "goal": parts[2] if len(parts) > 2 else "",
                    "flaw": parts[3] if len(parts) > 3 else "",
                    "arc": parts[4] if len(parts) > 4 else "",
                },
            )
        return characters
    return []


def _extract_factions(sections: list[MarkdownSection]) -> list[dict[str, str]]:
    factions: list[dict[str, str]] = []
    for sec in sections:
        lowered = sec.title.lower()
        if "势力" not in sec.title and "faction" not in lowered and "组织" not in sec.title:
            continue
        for bullet in extract_bullets(sec.lines):
            if "：" in bullet:
                name, desc = bullet.split("：", 1)
            elif ":" in bullet:
                name, desc = bullet.split(":", 1)
            else:
                name, desc = bullet, ""
            factions.append({"name": clean_sentence(name), "description": clean_sentence(desc)})
    return factions


def _extract_conflicts(sections: list[MarkdownSection]) -> dict[str, Any]:
    result = {"main_conflict": "", "secondary_conflicts": []}
    for sec in sections:
        lowered = sec.title.lower()
        if "冲突" not in sec.title and "conflict" not in lowered:
            continue
        kv = parse_key_values(sec.lines)
        result["main_conflict"] = kv.get("主冲突", kv.get("main_conflict", first_nonempty_line(sec.lines)))
        secondary = [
            item for item in (_drop_label_prefix(x) for x in extract_bullets(sec.lines)[:10])
            if "主冲突" not in item and "main_conflict" not in item.lower()
        ]
        main_normalized = clean_sentence(result["main_conflict"])
        result["secondary_conflicts"] = [
            item for item in secondary
            if clean_sentence(item) and clean_sentence(item) != main_normalized
        ]
        break
    return result


def _extract_constraints(sections: list[MarkdownSection]) -> dict[str, list[str]]:
    constraints = {"must_have": [], "must_avoid": []}
    for sec in sections:
        lowered = sec.title.lower()
        if "约束" not in sec.title and "constraints" not in lowered and "边界" not in sec.title:
            continue
        for bullet in extract_bullets(sec.lines):
            if bullet.lower().startswith("must-have") or bullet.startswith("必须"):
                constraints["must_have"].append(bullet)
            elif bullet.lower().startswith("must-avoid") or bullet.startswith("禁止") or bullet.startswith("避免"):
                constraints["must_avoid"].append(bullet)
            else:
                # Keep untagged items as must-have by default.
                constraints["must_have"].append(bullet)
    return constraints


def _to_int(raw: str, default: int) -> int:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return default
    try:
        return int(digits)
    except ValueError:
        return default


def _split_values(raw: str) -> list[str]:
    if not raw:
        return []
    replaced = raw.replace("，", ",").replace("、", ",").replace("；", ",")
    return [clean_sentence(item) for item in replaced.split(",") if clean_sentence(item)]


def _drop_label_prefix(text: str) -> str:
    for sep in ("：", ":"):
        if sep in text:
            left, right = text.split(sep, 1)
            if len(left) <= 8:
                return clean_sentence(right)
    return clean_sentence(text)

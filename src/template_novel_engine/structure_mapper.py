from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def map_structure(template_dna: dict[str, Any], story_bible: dict[str, Any]) -> tuple[dict[str, Any], str]:
    total_chapters = _resolve_total_chapters(template_dna, story_bible)
    stages = _build_stage_ranges(template_dna, total_chapters)
    mapped_stages = _map_stages(stages, template_dna, story_bible, total_chapters)
    chapter_plan = _build_chapter_plan(mapped_stages, total_chapters, story_bible)

    structure_map = {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "template_file": template_dna.get("source_file", ""),
            "story_file": story_bible.get("source_file", ""),
        },
        "book_title": story_bible.get("metadata", {}).get("title", "Untitled Story"),
        "target_chapters": total_chapters,
        "stage_contracts": mapped_stages,
        "chapter_plan": chapter_plan,
    }
    outline = _render_outline_markdown(structure_map, template_dna, story_bible)
    return structure_map, outline


def _resolve_total_chapters(template_dna: dict[str, Any], story_bible: dict[str, Any]) -> int:
    meta = story_bible.get("metadata", {})
    target = meta.get("target_chapters")
    if isinstance(target, int) and target > 0:
        return target

    beats = template_dna.get("rhythm_beats", [])
    if beats:
        return max(int(item.get("chapter_end", 1)) for item in beats)

    stages = template_dna.get("narrative_stages", [])
    if stages:
        return max(20, len(stages) * 6)
    return 40


def _build_stage_ranges(template_dna: dict[str, Any], total_chapters: int) -> list[dict[str, Any]]:
    beats = template_dna.get("rhythm_beats", [])
    if beats:
        ranges: list[dict[str, Any]] = []
        for idx, beat in enumerate(beats, start=1):
            ranges.append(
                {
                    "stage_id": f"stage_{idx:02d}",
                    "title": beat.get("objective", f"Stage {idx}"),
                    "chapter_start": int(beat.get("chapter_start", 1)),
                    "chapter_end": int(beat.get("chapter_end", min(total_chapters, idx * 5))),
                },
            )
        max_end = max(item["chapter_end"] for item in ranges)
        if max_end < total_chapters:
            ranges.append(
                {
                    "stage_id": f"stage_{len(ranges) + 1:02d}",
                    "title": "终局升维与规则改写",
                    "chapter_start": max_end + 1,
                    "chapter_end": total_chapters,
                },
            )
        return ranges

    template_stages = template_dna.get("narrative_stages", [])
    if not template_stages:
        return [
            {"stage_id": "stage_01", "title": "Hook", "chapter_start": 1, "chapter_end": max(1, total_chapters // 4)},
            {
                "stage_id": "stage_02",
                "title": "Escalation",
                "chapter_start": max(2, total_chapters // 4 + 1),
                "chapter_end": max(2, total_chapters // 2),
            },
            {
                "stage_id": "stage_03",
                "title": "Breakthrough",
                "chapter_start": max(3, total_chapters // 2 + 1),
                "chapter_end": max(3, (total_chapters * 3) // 4),
            },
            {
                "stage_id": "stage_04",
                "title": "Endgame",
                "chapter_start": max(4, (total_chapters * 3) // 4 + 1),
                "chapter_end": total_chapters,
            },
        ]

    # Even split fallback.
    count = len(template_stages)
    step = max(1, total_chapters // count)
    ranges: list[dict[str, Any]] = []
    for idx, stage in enumerate(template_stages, start=1):
        start = (idx - 1) * step + 1
        end = total_chapters if idx == count else min(total_chapters, idx * step)
        ranges.append(
            {
                "stage_id": stage.get("stage_id", f"stage_{idx:02d}"),
                "title": stage.get("title", f"Stage {idx}"),
                "chapter_start": start,
                "chapter_end": end,
                "template_summary": stage.get("summary", ""),
                "template_points": stage.get("key_points", []),
            },
        )
    return ranges


def _map_stages(
    stage_ranges: list[dict[str, Any]],
    template_dna: dict[str, Any],
    story_bible: dict[str, Any],
    total_chapters: int,
) -> list[dict[str, Any]]:
    main_conflict = story_bible.get("conflicts", {}).get("main_conflict", "Main conflict unresolved.")
    secondary = story_bible.get("conflicts", {}).get("secondary_conflicts", [])
    characters = story_bible.get("characters", [])
    protagonist = characters[0]["name"] if characters else "Protagonist"
    factions = [f.get("name", "") for f in story_bible.get("factions", []) if f.get("name")]
    locations = story_bible.get("world", {}).get("locations", [])
    principles = [p.get("detail") for p in template_dna.get("principles", []) if p.get("detail")]

    mapped: list[dict[str, Any]] = []
    for idx, stage in enumerate(stage_ranges, start=1):
        title = str(stage.get("title", f"Stage {idx}"))
        stage_goal = _generate_stage_goal(title, idx, protagonist, main_conflict, secondary)
        escalation_target = _pick_escalation_target(title, idx, total_chapters)
        mapped.append(
            {
                "stage_id": stage["stage_id"],
                "template_title": title,
                "chapter_start": stage["chapter_start"],
                "chapter_end": stage["chapter_end"],
                "story_goal": stage_goal,
                "must_keep": _pick_must_keep(principles),
                "escalation_target": escalation_target,
                "pov_focus": [protagonist],
                "setpiece_candidates": _pick_setpieces(locations, factions, idx),
            },
        )
    return mapped


def _build_chapter_plan(
    mapped_stages: list[dict[str, Any]],
    total_chapters: int,
    story_bible: dict[str, Any],
) -> list[dict[str, Any]]:
    title = story_bible.get("metadata", {}).get("title", "Untitled Story")
    plan: list[dict[str, Any]] = []

    stage_by_chapter: dict[int, dict[str, Any]] = {}
    for stage in mapped_stages:
        for chapter in range(stage["chapter_start"], stage["chapter_end"] + 1):
            stage_by_chapter[chapter] = stage

    for chapter_no in range(1, total_chapters + 1):
        stage = stage_by_chapter.get(chapter_no, mapped_stages[-1])
        local_index = chapter_no - stage["chapter_start"] + 1
        local_total = stage["chapter_end"] - stage["chapter_start"] + 1
        beat = _chapter_beat(local_index, local_total, stage["story_goal"])
        plan.append(
            {
                "chapter": chapter_no,
                "title": f"{title} - Chapter {chapter_no}",
                "stage_id": stage["stage_id"],
                "objective": beat,
            },
        )
    return plan


def _generate_stage_goal(
    title: str,
    stage_index: int,
    protagonist: str,
    main_conflict: str,
    secondary_conflicts: list[str],
) -> str:
    lowered = title.lower()
    if "钩子" in title or "hook" in lowered:
        return f"用高冲击真相推翻旧认知，把读者迅速拉入主冲突：{main_conflict}"
    if "翻案" in title or "breakthrough" in lowered:
        return f"让{protagonist}拿回主体性，完成第一次明确翻盘。"
    if "清算" in title or "escalation" in lowered:
        return "把冲突从个人恩怨升级为体系对抗。"
    if "终局" in title or "endgame" in lowered:
        return "进入终局战场，以价值立场与规则重写收束，而非单纯堆战力。"
    if secondary_conflicts:
        return f"推进支线矛盾：{secondary_conflicts[(stage_index - 1) % len(secondary_conflicts)]}，并持续服务主冲突。"
    return f"阶段{stage_index}主任务：推进主冲突并制造下一阶段升级压力。"


def _pick_escalation_target(title: str, stage_index: int, total_chapters: int) -> str:
    if "钩子" in title or "hook" in title.lower():
        return "完成读者站队与首个情绪补偿点。"
    if stage_index == 1:
        return "在10章前给出首个硬兑现。"
    if stage_index >= 4 or "终局" in title:
        return f"进入最终收束窗口（最后{max(5, total_chapters // 6)}章）。"
    return "提升冲突层级并扩大战场范围。"


def _pick_must_keep(principles: list[str]) -> list[str]:
    base = [
        "主角主体性必须持续在线，不能沦为挂件。",
        "每个阶段至少完成一次可感知兑现。",
    ]
    for p in principles[:3]:
        if p and p not in base:
            base.append(p)
    return base[:5]


def _pick_setpieces(locations: list[str], factions: list[str], stage_index: int) -> list[str]:
    picks: list[str] = []
    if locations:
        picks.append(locations[(stage_index - 1) % len(locations)])
    if factions:
        picks.append(factions[(stage_index - 1) % len(factions)])
    if not picks:
        picks = ["public confrontation", "private truth reveal"]
    return picks


def _chapter_beat(local_index: int, local_total: int, stage_goal: str) -> str:
    if local_total <= 1:
        return stage_goal
    if local_index == 1:
        return f"阶段入场节拍：立即制造紧张感。{stage_goal}"
    if local_index == local_total:
        return "阶段兑现节拍：回收当前承诺并抛出下一阶段压力。"
    midpoint = max(2, local_total // 2)
    if local_index == midpoint:
        return "中段反转节拍：迫使角色做不可逆选择。"
    return "推进节拍：新增阻力、信息揭示或关系变化。"


def _render_outline_markdown(
    structure_map: dict[str, Any],
    template_dna: dict[str, Any],
    story_bible: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# Volume Outline - {structure_map['book_title']}")
    lines.append("")
    lines.append("## Core Inputs")
    lines.append(f"- Template source: {template_dna.get('source_file', '')}")
    lines.append(f"- Story source: {story_bible.get('source_file', '')}")
    lines.append(f"- Target chapters: {structure_map.get('target_chapters', 0)}")
    lines.append("")
    lines.append("## Stage Contracts")
    for stage in structure_map["stage_contracts"]:
        lines.append(f"### {stage['stage_id']} | Chapter {stage['chapter_start']}-{stage['chapter_end']}")
        lines.append(f"- Template anchor: {stage['template_title']}")
        lines.append(f"- Story goal: {stage['story_goal']}")
        lines.append(f"- Escalation target: {stage['escalation_target']}")
        lines.append(f"- Must keep: {'; '.join(stage['must_keep'])}")
        lines.append(f"- Setpieces: {'; '.join(stage['setpiece_candidates'])}")
        lines.append("")

    lines.append("## Chapter Plan")
    for item in structure_map["chapter_plan"]:
        lines.append(f"- Chapter {item['chapter']} [{item['stage_id']}]: {item['objective']}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Callable

from .audit_reviser import run_t7_audit_and_revise
from .chapter_analyzer import analyze_chapter
from .context_engine import compose_context, seed_runtime_state
from .model_writer import (
    generate_chapter_draft_with_llm,
    normalize_writer_config,
    writer_public_profile,
)
from .state_reflector import apply_t6_state_reflection, render_t6_report_markdown


def run_t5_pipeline(
    template_dna: dict[str, Any],
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
    runtime_state: dict[str, Any] | None,
    chapter_start: int,
    chapter_end: int,
    token_budget: int = 1800,
    out_dir: str = "",
    author_intent: str = "",
    writer_config: dict[str, Any] | None = None,
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
    on_chapter_complete: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if chapter_start <= 0 or chapter_end <= 0:
        raise ValueError("chapter_start/chapter_end must be positive.")
    if chapter_end < chapter_start:
        raise ValueError("chapter_end must be >= chapter_start.")

    output_root = Path(out_dir) if out_dir else None
    if output_root:
        output_root.mkdir(parents=True, exist_ok=True)

    runtime = deepcopy(runtime_state) if runtime_state else seed_runtime_state(story_bible, structure_map)
    resolved_writer = normalize_writer_config(writer_config)
    chapter_packages: list[dict[str, Any]] = []
    alignment_all_passed = True
    total_chapters = chapter_end - chapter_start + 1

    for chapter_offset, chapter_no in enumerate(range(chapter_start, chapter_end + 1), start=1):
        chapter_started_at = time.perf_counter()
        print(
            f"[PROGRESS] chapter {chapter_no} start ({chapter_offset}/{total_chapters})",
            flush=True,
        )
        try:
            contract = plan_chapter(structure_map, story_bible, runtime, chapter_no)
            contract["length_control_enabled"] = bool(
                resolved_writer.get("length_control", {}).get("enabled", True),
            )
            context_bundle, context_report_md, runtime_from_context = compose_context(
                template_dna=template_dna,
                story_bible=story_bible,
                structure_map=structure_map,
                runtime_state=runtime,
                chapter_no=chapter_no,
                token_budget=token_budget,
                author_intent=author_intent,
                runtime_prompt_view_cfg=runtime_prompt_view_cfg,
            )
            context_bundle["precheck"] = build_precheck(contract, context_bundle, chapter_no)
            draft_md, chapter_summary, writer_meta = write_draft(
                template_dna=template_dna,
                story_bible=story_bible,
                contract=contract,
                context_bundle=context_bundle,
                chapter_no=chapter_no,
                writer_config=resolved_writer,
            )
            _update_writer_length_profile(resolved_writer, writer_meta)
            alignment = audit_template_alignment(structure_map, contract, chapter_no)
            alignment_all_passed = alignment_all_passed and alignment["pass"]

            audited_draft, t7_audit_report, t7_diff_md = run_t7_audit_and_revise(
                chapter_no=chapter_no,
                draft_markdown=draft_md,
                contract=contract,
                alignment_report=alignment,
                story_bible=story_bible,
                structure_map=structure_map,
                runtime_state=runtime_from_context,
                auto_revise=True,
            )
            if audited_draft != draft_md:
                chapter_summary = f"{chapter_summary} [T7 revised once]"

            chapter_analysis = analyze_chapter(
                chapter_no=chapter_no,
                draft_markdown=audited_draft,
                chapter_summary=chapter_summary,
                story_bible=story_bible,
                runtime_state=runtime_from_context,
            )
            runtime, state_delta, t6_report = apply_t6_state_reflection(
                runtime_state=runtime_from_context,
                story_bible=story_bible,
                chapter_no=chapter_no,
                draft_markdown=audited_draft,
                chapter_summary=chapter_summary,
                contract=contract,
                alignment=alignment,
                chapter_analysis=chapter_analysis,
                audit_report=t7_audit_report,
                author_intent=author_intent,
                runtime_prompt_view_cfg=runtime_prompt_view_cfg,
            )

            package = {
                "schema_version": "v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "chapter": chapter_no,
                "contract": contract,
                "context_bundle": context_bundle,
                "alignment_report": alignment,
                "draft_markdown": audited_draft,
                "draft_markdown_raw": draft_md,
                "chapter_summary": chapter_summary,
                "chapter_analysis": chapter_analysis,
                "t7_audit_report": t7_audit_report,
                "t7_diff_report_md": t7_diff_md,
                "state_delta": state_delta,
                "t6_report": t6_report,
                "runtime_quality_history": deepcopy(runtime.get("quality_history", [])),
                "writer": writer_meta,
            }
            chapter_packages.append(package)

            if output_root:
                _write_outputs_per_chapter(
                    output_root=output_root,
                    chapter_no=chapter_no,
                    package=package,
                    context_report_md=context_report_md,
                    draft_md=audited_draft,
                    t7_diff_md=t7_diff_md,
                    t6_report_md=render_t6_report_markdown(t6_report),
                )
            if on_chapter_complete:
                on_chapter_complete(package)
        except Exception as exc:
            elapsed = time.perf_counter() - chapter_started_at
            print(
                f"[ERROR] chapter {chapter_no} failed after {elapsed:.1f}s: {exc}",
                flush=True,
            )
            raise RuntimeError(f"chapter {chapter_no} failed: {exc}") from exc

        elapsed = time.perf_counter() - chapter_started_at
        t7_pass = bool(package.get("t7_audit_report", {}).get("after", {}).get("pass", False))
        writer_attempts = int(
            package.get("writer", {}).get("length_control", {}).get("attempts", 1) or 1,
        )
        print(
            f"[PROGRESS] chapter {chapter_no} done in {elapsed:.1f}s "
            f"(alignment={alignment.get('pass', False)}, t7={t7_pass}, writer_attempts={writer_attempts})",
            flush=True,
        )

    summary = build_t5_summary(
        story_bible=story_bible,
        chapter_start=chapter_start,
        chapter_end=chapter_end,
        chapter_packages=chapter_packages,
        alignment_all_passed=alignment_all_passed,
        writer_profile=writer_public_profile(resolved_writer),
    )
    if output_root:
        _write_json(output_root / "t5_summary.json", summary)
        _write_text(output_root / "t5_summary.md", render_t5_summary_markdown(summary))
        _write_json(output_root / "runtime_state_after_t5.json", runtime)

    return summary, runtime


def plan_chapter(
    structure_map: dict[str, Any],
    story_bible: dict[str, Any],
    runtime_state: dict[str, Any],
    chapter_no: int,
) -> dict[str, Any]:
    chapter_plan_item = _find_chapter_plan(structure_map, chapter_no)
    stage_contract = _find_stage_contract(structure_map, chapter_no)
    metadata = story_bible.get("metadata", {})

    protagonist = _resolve_protagonist(story_bible)
    focus = runtime_state.get("current_focus", "") or runtime_state.get("author_intent", "")
    if not focus:
        focus = stage_contract.get("story_goal", "")
    chapter_word_target = _safe_int(metadata.get("chapter_word_target"), 3000)
    chapter_word_target = max(500, min(20000, chapter_word_target))
    chapter_word_tolerance_ratio = _safe_float(metadata.get("chapter_word_tolerance_ratio"), 0.15)
    chapter_word_tolerance_ratio = min(0.45, max(0.05, chapter_word_tolerance_ratio))

    return {
        "chapter": chapter_no,
        "chapter_title": chapter_plan_item.get("title", f"Chapter {chapter_no}"),
        "stage_id": stage_contract.get("stage_id", ""),
        "stage_range": {
            "chapter_start": int(stage_contract.get("chapter_start", chapter_no)),
            "chapter_end": int(stage_contract.get("chapter_end", chapter_no)),
        },
        "template_anchor": stage_contract.get("template_title", ""),
        "chapter_objective": chapter_plan_item.get("objective", ""),
        "stage_goal": stage_contract.get("story_goal", ""),
        "must_keep": stage_contract.get("must_keep", []),
        "escalation_target": stage_contract.get("escalation_target", ""),
        "focus_character": protagonist,
        "author_focus": focus,
        "chapter_word_target": chapter_word_target,
        "chapter_word_tolerance_ratio": chapter_word_tolerance_ratio,
        "forbidden": [
            "Do not consume the final climax in advance.",
            "Do not skip unresolved mandatory threads.",
            "Do not violate hard world rules.",
        ],
        "planned_beats": _plan_beats(chapter_no, chapter_plan_item.get("objective", ""), protagonist),
    }


def build_precheck(contract: dict[str, Any], context_bundle: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    warnings: list[str] = []
    objective = str(contract.get("chapter_objective", "")).strip()
    if len(objective) < 6:
        warnings.append("当前章目标过短，容易导致推进不足。")

    continuation = context_bundle.get("continuation_anchor", {})
    if chapter_no > 1 and not continuation.get("tail"):
        warnings.append("缺少上一章尾部承接锚点。")

    anti_repetition = context_bundle.get("recent_progress", {}).get("anti_repetition", [])
    if isinstance(anti_repetition, list) and anti_repetition:
        warnings.append(f"避免重复：{anti_repetition[0]}")

    return {"warnings": warnings}


def write_draft(
    template_dna: dict[str, Any],
    story_bible: dict[str, Any],
    contract: dict[str, Any],
    context_bundle: dict[str, Any],
    chapter_no: int,
    writer_config: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    writer = normalize_writer_config(writer_config)
    backend = str(writer.get("backend", "builtin")).lower()
    if backend in {"openai", "claude"}:
        return generate_chapter_draft_with_llm(
            template_dna=template_dna,
            story_bible=story_bible,
            contract=contract,
            context_bundle=context_bundle,
            chapter_no=chapter_no,
            writer_config=writer,
        )

    title = contract.get("chapter_title", f"Chapter {chapter_no}")
    protagonist = contract.get("focus_character", "主角")
    mentor = _find_character_by_role(story_bible, "mentor")
    antagonist = _find_character_by_role(story_bible, "antagonist")
    location = _pick_location_for_chapter(story_bible, chapter_no)

    chapter_objective = contract.get("chapter_objective", "")
    stage_goal = contract.get("stage_goal", "")
    escalation = contract.get("escalation_target", "")
    must_keep = contract.get("must_keep", [])[:3]
    hard_facts_preview = context_bundle.get("tiers", {}).get("tier_0_hard_facts", {}).get("items", [])[:2]
    hard_fact_hint = "；".join(item.get("text", "") for item in hard_facts_preview if item.get("text"))

    p1 = (
        f"{location}的风像刀背一样刮过街口，{protagonist}在进入现场前先确认底线："
        f"本章必须完成“{chapter_objective}”，否则阶段推进会失真。"
    )
    p2 = (
        f"{protagonist}没有等待外援，而是主动拆分风险，先做低暴露试探，再推进关键动作。"
        f"这一步直接服务于阶段目标“{stage_goal}”，不是热闹情节，而是结构推进。"
    )
    p3 = (
        f"{mentor}只提供必要支撑，不替代决策；{antagonist}试图用既有秩序重新解释危机，"
        "把真相压回可控叙事。"
    )
    p4 = (
        f"对抗不落在口号上，而落在可追踪事实：{hard_fact_hint or '关键证据被当场钉死'}。"
        f"{protagonist}由被动应对转为主动施压，迫使局面进入不可逆变化。"
    )
    p5 = (
        f"章节收束时，{protagonist}完成当章兑现，并抛出下一轮压力“{escalation}”。"
        f"他保留三条约束：{'; '.join(must_keep) if must_keep else '主冲突连续、高潮不越级消耗、伏笔可回收'}。"
    )

    draft_lines = [
        f"# {title}",
        "",
        "## 正文",
        p1,
        "",
        p2,
        "",
        p3,
        "",
        p4,
        "",
        p5,
        "",
        "## 本章模板对齐点",
        f"- 阶段: {contract.get('stage_id', '')} ({contract.get('stage_range', {}).get('chapter_start', '')}-{contract.get('stage_range', {}).get('chapter_end', '')})",
        f"- 结构任务: {chapter_objective}",
        f"- 阶段目标: {stage_goal}",
        f"- 升级目标: {escalation}",
    ]
    summary = f"{protagonist}在{location}推进“{chapter_objective}”，完成当章兑现并将冲突抬升到“{escalation}”。"
    return (
        "\n".join(draft_lines).strip() + "\n",
        summary,
        {
            "backend": "builtin",
            "model": "rule-template-v1",
            "latency_ms": 0,
            "usage": {},
        },
    )


def audit_template_alignment(
    structure_map: dict[str, Any],
    contract: dict[str, Any],
    chapter_no: int,
) -> dict[str, Any]:
    stage_expected = _find_stage_contract(structure_map, chapter_no)
    stage_actual = contract.get("stage_id", "")
    stage_pass = stage_expected.get("stage_id", "") == stage_actual

    objective_expected = _find_chapter_plan(structure_map, chapter_no).get("objective", "")
    objective_actual = contract.get("chapter_objective", "")
    objective_pass = bool(objective_expected) and objective_expected == objective_actual

    completed_tasks = [
        f"stage_locked={stage_actual}",
        "chapter objective carried into contract",
        "stage escalation target preserved",
    ]
    failed_checks: list[str] = []
    if not stage_pass:
        failed_checks.append("stage mismatch")
    if not objective_pass:
        failed_checks.append("objective mismatch")

    return {
        "chapter": chapter_no,
        "pass": stage_pass and objective_pass,
        "checks": {
            "stage_order": stage_pass,
            "objective_alignment": objective_pass,
        },
        "expected": {
            "stage_id": stage_expected.get("stage_id", ""),
            "objective": objective_expected,
        },
        "actual": {
            "stage_id": stage_actual,
            "objective": objective_actual,
        },
        "completed_template_tasks": completed_tasks,
        "failed_checks": failed_checks,
    }


def reflect_state_minimal(
    runtime_state: dict[str, Any],
    chapter_no: int,
    chapter_summary: str,
    contract: dict[str, Any],
    alignment: dict[str, Any],
    author_intent: str = "",
) -> dict[str, Any]:
    runtime = deepcopy(runtime_state)
    runtime["current_chapter"] = chapter_no
    if author_intent.strip():
        runtime["author_intent"] = author_intent.strip()
        runtime["current_focus"] = author_intent.strip()
    else:
        runtime["current_focus"] = contract.get("chapter_objective", "")

    summaries = runtime.setdefault("chapter_summaries", [])
    summaries.append(
        {
            "chapter": chapter_no,
            "summary": chapter_summary,
            "stage_id": contract.get("stage_id", ""),
            "objective": contract.get("chapter_objective", ""),
            "alignment_pass": alignment.get("pass", False),
        },
    )
    runtime["chapter_summaries"] = summaries[-120:]

    active_threads = runtime.setdefault("active_threads", [])
    thread_ledger = runtime.setdefault("thread_ledger", [])

    updated_threads: list[dict[str, Any]] = []
    for idx, thread in enumerate(active_threads):
        record = deepcopy(thread) if isinstance(thread, dict) else {"title": str(thread)}
        due = _safe_int(record.get("due_chapter"), 9999)
        status = str(record.get("status", "active")).lower()
        if status not in {"resolved", "closed"}:
            if chapter_no > due:
                status = "overdue"
            elif chapter_no == due:
                status = "due"
            elif status == "overdue":
                status = "active"
        if idx == 0:
            record["last_updated_chapter"] = chapter_no
            record["note"] = f"Progress touched by chapter {chapter_no}: {contract.get('chapter_objective', '')}"
        record["status"] = status
        updated_threads.append(record)

    runtime["active_threads"] = updated_threads
    runtime["thread_ledger"] = deepcopy(updated_threads) if updated_threads else thread_ledger
    runtime["last_alignment"] = alignment
    runtime["updated_at"] = datetime.now(timezone.utc).isoformat()
    return runtime


def build_t5_summary(
    story_bible: dict[str, Any],
    chapter_start: int,
    chapter_end: int,
    chapter_packages: list[dict[str, Any]],
    alignment_all_passed: bool,
    writer_profile: dict[str, Any],
) -> dict[str, Any]:
    alignment_matrix = []
    length_rows = []
    for pkg in chapter_packages:
        alignment = pkg.get("alignment_report", {})
        length_meta = pkg.get("writer", {}).get("length_control", {})
        alignment_matrix.append(
            {
                "chapter": pkg.get("chapter"),
                "stage_id": pkg.get("contract", {}).get("stage_id", ""),
                "alignment_pass": alignment.get("pass", False),
            },
        )
        if isinstance(length_meta, dict) and length_meta:
            length_rows.append(
                {
                    "chapter": pkg.get("chapter"),
                    "target_chars": int(length_meta.get("target_chars", 0) or 0),
                    "actual_chars": int(length_meta.get("actual_chars", 0) or 0),
                    "within_range": bool(length_meta.get("within_range", False)),
                    "attempts": int(length_meta.get("attempts", 0) or 0),
                },
            )

    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "book_title": story_bible.get("metadata", {}).get("title", "Untitled Story"),
        "chapter_range": [chapter_start, chapter_end],
        "chapter_count": len(chapter_packages),
        "dod": {
            "chapter_contract_generated": all(bool(pkg.get("contract")) for pkg in chapter_packages),
            "chapter_draft_generated": all(bool(pkg.get("draft_markdown")) for pkg in chapter_packages),
            "rhythm_alignment_passed": alignment_all_passed,
        },
        "t6_dod": {
            "state_delta_generated": all(bool(pkg.get("state_delta")) for pkg in chapter_packages),
            "foreshadow_trackable": all(
                bool(pkg.get("t6_report", {}).get("trackability_ok", False))
                for pkg in chapter_packages
            ),
        },
        "analysis_dod": {
            "analysis_generated": all(bool(pkg.get("chapter_analysis")) for pkg in chapter_packages),
            "character_state_extracted": all(
                isinstance(pkg.get("chapter_analysis", {}).get("character_states", []), list)
                for pkg in chapter_packages
            ),
        },
        "t7_dod": {
            "audit_generated": all(bool(pkg.get("t7_audit_report")) for pkg in chapter_packages),
            "auto_revision_once_enabled": all(
                int(pkg.get("t7_audit_report", {}).get("revision", {}).get("max_attempts", 0)) == 1
                for pkg in chapter_packages
            ),
            "post_audit_pass": all(
                bool(pkg.get("t7_audit_report", {}).get("after", {}).get("pass", False))
                for pkg in chapter_packages
            ),
            "diff_report_generated": all(bool(pkg.get("t7_diff_report_md", "")) for pkg in chapter_packages),
        },
        "writer": writer_profile,
        "alignment_matrix": alignment_matrix,
        "length_control": {
            "enabled": bool(length_rows),
            "in_range_count": sum(1 for row in length_rows if row.get("within_range", False)),
            "out_of_range_count": sum(1 for row in length_rows if not row.get("within_range", False)),
            "rows": length_rows,
        },
    }


def render_t5_summary_markdown(summary: dict[str, Any]) -> str:
    dod = summary.get("dod", {})
    writer = summary.get("writer", {})
    lines = [
        f"# T5 Summary - {summary.get('book_title', '')}",
        "",
        "## Range",
        f"- Chapter range: {summary.get('chapter_range', ['?', '?'])[0]}-{summary.get('chapter_range', ['?', '?'])[1]}",
        f"- Chapter count: {summary.get('chapter_count', 0)}",
        "",
        "## DoD",
        f"- Chapter contract generated: {dod.get('chapter_contract_generated', False)}",
        f"- Chapter draft generated: {dod.get('chapter_draft_generated', False)}",
        f"- Rhythm alignment passed: {dod.get('rhythm_alignment_passed', False)}",
        "",
        "## Writer",
        f"- backend: {writer.get('backend', 'builtin')}",
        f"- model: {writer.get('model', '')}",
        f"- temperature: {writer.get('temperature', 0)}",
        f"- max_tokens: {writer.get('max_tokens', 0)}",
        "",
        "## Alignment Matrix",
    ]
    for row in summary.get("alignment_matrix", []):
        lines.append(
            f"- Chapter {row.get('chapter')}: stage={row.get('stage_id', '')}, pass={row.get('alignment_pass', False)}",
        )
    t6 = summary.get("t6_dod", {})
    if t6:
        lines.extend(
            [
                "",
                "## T6 DoD",
                f"- state delta generated: {t6.get('state_delta_generated', False)}",
                f"- foreshadow trackable: {t6.get('foreshadow_trackable', False)}",
            ],
        )
    t7 = summary.get("t7_dod", {})
    if t7:
        lines.extend(
            [
                "",
                "## T7 DoD",
                f"- audit generated: {t7.get('audit_generated', False)}",
                f"- auto revision once enabled: {t7.get('auto_revision_once_enabled', False)}",
                f"- post-audit pass: {t7.get('post_audit_pass', False)}",
                f"- diff report generated: {t7.get('diff_report_generated', False)}",
            ],
        )
    t7_batch = summary.get("t7_batch_auto", {})
    if t7_batch:
        lines.extend(
            [
                "",
                "## T7 Batch Auto",
                f"- enabled: {t7_batch.get('enabled', False)}",
                f"- pass: {t7_batch.get('pass', False)}",
                f"- out dir: {t7_batch.get('out_dir', '')}",
                f"- summary file: {t7_batch.get('summary_file', '')}",
            ],
        )
    length_summary = summary.get("length_control", {})
    if length_summary:
        lines.extend(
            [
                "",
                "## Length Control",
                f"- in-range: {length_summary.get('in_range_count', 0)}",
                f"- out-of-range: {length_summary.get('out_of_range_count', 0)}",
            ],
        )
    lines.append("")
    return "\n".join(lines)


def _write_outputs_per_chapter(
    output_root: Path,
    chapter_no: int,
    package: dict[str, Any],
    context_report_md: str,
    draft_md: str,
    t7_diff_md: str,
    t6_report_md: str,
) -> None:
    suffix = f"ch{chapter_no:02d}"
    _write_json(output_root / f"chapter_contract_{suffix}.json", package["contract"])
    _write_json(output_root / f"context_bundle_{suffix}.json", package["context_bundle"])
    _write_text(output_root / f"context_report_{suffix}.md", context_report_md)
    _write_json(output_root / f"alignment_report_{suffix}.json", package["alignment_report"])
    _write_json(output_root / f"chapter_analysis_{suffix}.json", package.get("chapter_analysis", {}))
    _write_json(output_root / f"t7_audit_report_{suffix}.json", package["t7_audit_report"])
    _write_text(output_root / f"t7_diff_report_{suffix}.md", t7_diff_md)
    _write_json(output_root / f"state_delta_{suffix}.json", package["state_delta"])
    _write_json(output_root / f"t6_report_{suffix}.json", package["t6_report"])
    _write_text(output_root / f"t6_report_{suffix}.md", t6_report_md)
    _write_text(output_root / f"chapter_draft_{suffix}.md", draft_md)
    _write_json(output_root / f"chapter_package_{suffix}.json", package)


def _find_stage_contract(structure_map: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    for stage in structure_map.get("stage_contracts", []):
        start = int(stage.get("chapter_start", 1))
        end = int(stage.get("chapter_end", start))
        if start <= chapter_no <= end:
            return stage
    contracts = structure_map.get("stage_contracts", [])
    if contracts:
        return contracts[-1]
    return {
        "stage_id": "stage_01",
        "chapter_start": chapter_no,
        "chapter_end": chapter_no,
        "template_title": "Stage",
        "story_goal": "",
        "must_keep": [],
        "escalation_target": "",
    }


def _find_chapter_plan(structure_map: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    for item in structure_map.get("chapter_plan", []):
        if int(item.get("chapter", -1)) == chapter_no:
            return item
    return {
        "chapter": chapter_no,
        "title": f"Chapter {chapter_no}",
        "stage_id": _find_stage_contract(structure_map, chapter_no).get("stage_id", "stage_01"),
        "objective": "",
    }


def _resolve_protagonist(story_bible: dict[str, Any]) -> str:
    chars = story_bible.get("characters", [])
    for ch in chars:
        if str(ch.get("role", "")).lower() == "protagonist":
            return ch.get("name", "主角")
    if chars:
        return chars[0].get("name", "主角")
    return "主角"


def _find_character_by_role(story_bible: dict[str, Any], role: str) -> str:
    role = role.lower()
    for ch in story_bible.get("characters", []):
        if str(ch.get("role", "")).lower() == role:
            return ch.get("name", role)
    if story_bible.get("characters"):
        if role == "mentor":
            return story_bible["characters"][0].get("name", "盟友")
        if role == "antagonist":
            return story_bible["characters"][-1].get("name", "对手")
    return "关键角色"


def _pick_location_for_chapter(story_bible: dict[str, Any], chapter_no: int) -> str:
    locations = story_bible.get("world", {}).get("locations", [])
    if not locations:
        return "主场景"
    return str(locations[(chapter_no - 1) % len(locations)])


def _plan_beats(chapter_no: int, objective: str, protagonist: str) -> list[str]:
    return [
        f"Beat-1 开场压迫：让{protagonist}立刻面临与“{objective}”相关的现实阻力。",
        "Beat-2 中段反压：制造一个不可回避的决策岔路，迫使角色做选择。",
        "Beat-3 章尾兑现：完成本章承诺，并将压力抬升到下章。",
    ]


def _safe_int(raw: Any, default: int) -> int:
    if isinstance(raw, int):
        return raw
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if not digits:
        return default
    try:
        return int(digits)
    except ValueError:
        return default


def _safe_float(raw: Any, default: float) -> float:
    if isinstance(raw, bool):
        return float(int(raw))
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _update_writer_length_profile(writer_config: dict[str, Any], writer_meta: dict[str, Any]) -> None:
    if not isinstance(writer_config, dict) or not isinstance(writer_meta, dict):
        return
    length_meta = writer_meta.get("length_control", {})
    if not isinstance(length_meta, dict):
        return
    next_est = length_meta.get("token_per_char_est")
    if next_est is None:
        return
    length_cfg = writer_config.get("length_control", {})
    if not isinstance(length_cfg, dict):
        return
    try:
        value = float(next_est)
    except (TypeError, ValueError):
        return
    lower = float(length_cfg.get("token_per_char_min", 0.4))
    upper = float(length_cfg.get("token_per_char_max", 1.8))
    length_cfg["token_per_char_est"] = max(lower, min(upper, value))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_pretty_json(data), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _to_pretty_json(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2)


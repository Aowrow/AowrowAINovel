from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any


DEFAULT_TOKEN_BUDGET = 1800
DEFAULT_RUNTIME_PROMPT_VIEW_CONFIG: dict[str, Any] = {
    "enabled": True,
    "shadow_mode": True,
    "chapter_summaries_recent": 3,
    "threads_max": 8,
    "foreshadow_due_horizon": 3,
    "foreshadows_max": 8,
    "enable_digests": False,
    "digest_max_chars": 220,
}


def compose_context(
    template_dna: dict[str, Any],
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
    runtime_state: dict[str, Any] | None,
    chapter_no: int,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    author_intent: str = "",
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    runtime = _prepare_runtime_state(runtime_state, story_bible, structure_map, chapter_no)
    if author_intent.strip():
        runtime["author_intent"] = author_intent.strip()
    prompt_view_cfg = _normalize_runtime_prompt_view_config(runtime_prompt_view_cfg)
    prompt_view = _resolve_runtime_prompt_view(runtime, prompt_view_cfg)
    use_prompt_view = bool(prompt_view_cfg.get("enabled", True)) and not bool(prompt_view_cfg.get("shadow_mode", True))
    prompt_view_for_tiers = prompt_view if use_prompt_view else None

    stage_contract = _find_stage_contract(structure_map, chapter_no)
    chapter_objective = _find_chapter_objective(structure_map, chapter_no)

    tier0 = _build_tier_0_hard_facts(story_bible, runtime, stage_contract)
    tier1 = _build_tier_1_stage_contract(stage_contract, chapter_objective, chapter_no)
    tier2 = _build_tier_2_active_threads(
        story_bible=story_bible,
        runtime_state=runtime,
        chapter_no=chapter_no,
        runtime_prompt_view=prompt_view_for_tiers,
    )
    tier3 = _build_tier_3_retrieval_evidence(
        template_dna=template_dna,
        story_bible=story_bible,
        structure_map=structure_map,
        runtime_state=runtime,
        chapter_no=chapter_no,
        stage_contract=stage_contract,
        tier2=tier2,
        runtime_prompt_view=prompt_view_for_tiers,
    )

    packed, compression_log = _apply_budget_strategy(
        tier0=tier0,
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        token_budget=max(128, token_budget),
    )

    invariants = {
        "non_dropping_policy": True,
        "mandatory_tiers_never_dropped": True,
        "tier_0_original_count": len(tier0),
        "tier_1_original_count": len(tier1),
        "tier_0_final_count": len(packed["tier_0"]),
        "tier_1_final_count": len(packed["tier_1"]),
        "tier_0_dropped": len(tier0) - len(packed["tier_0"]),
        "tier_1_dropped": len(tier1) - len(packed["tier_1"]),
        "compression_order": ["tier_3", "tier_2"],
    }

    budget_report = {
        "token_budget": max(128, token_budget),
        "estimated_tokens": _estimate_total_tokens(
            packed["tier_0"],
            packed["tier_1"],
            packed["tier_2"],
            packed["tier_3"],
        ),
        "budget_met": _estimate_total_tokens(
            packed["tier_0"],
            packed["tier_1"],
            packed["tier_2"],
            packed["tier_3"],
        )
        <= max(128, token_budget),
    }

    bundle = {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapter": chapter_no,
        "book_title": story_bible.get("metadata", {}).get("title", "Untitled Story"),
        "continuation_anchor": deepcopy(runtime.get("continuation_anchor", {})),
        "recent_progress": deepcopy(runtime.get("recent_progress", {})),
        "tiers": {
            "tier_0_hard_facts": {
                "items": packed["tier_0"],
                "estimated_tokens": _estimate_items_tokens(packed["tier_0"]),
            },
            "tier_1_stage_contract": {
                "items": packed["tier_1"],
                "estimated_tokens": _estimate_items_tokens(packed["tier_1"]),
            },
            "tier_2_active_threads": {
                "items": packed["tier_2"],
                "estimated_tokens": _estimate_items_tokens(packed["tier_2"]),
            },
            "tier_3_retrieval_evidence": {
                "items": packed["tier_3"],
                "estimated_tokens": _estimate_items_tokens(packed["tier_3"]),
            },
        },
        "prompt_blocks": {
            "tier_0_hard_facts": _render_tier_block(packed["tier_0"]),
            "tier_1_stage_contract": _render_tier_block(packed["tier_1"]),
            "tier_2_active_threads": _render_tier_block(packed["tier_2"]),
            "tier_3_retrieval_evidence": _render_tier_block(packed["tier_3"]),
            "full_context": _render_full_context(packed),
        },
        "budget_report": budget_report,
        "invariants": invariants,
        "compression_log": compression_log,
        "prompt_view_report": {
            "enabled": bool(prompt_view_cfg.get("enabled", True)),
            "shadow_mode": bool(prompt_view_cfg.get("shadow_mode", True)),
            "source_mode": "runtime_prompt_view" if use_prompt_view else "runtime_state_raw",
            "stats": prompt_view.get("stats", {}) if isinstance(prompt_view, dict) else {},
        },
    }
    report_md = _render_budget_report_markdown(bundle)
    return bundle, report_md, runtime


def seed_runtime_state(
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
) -> dict[str, Any]:
    chars = story_bible.get("characters", [])
    character_states = []
    for ch in chars:
        character_states.append(
            {
                "name": ch.get("name", "Unknown"),
                "status": "active",
                "survival_status": "active",
                "current_state": "",
                "position": "unknown",
                "last_updated_chapter": 0,
            },
        )

    main_conflict = story_bible.get("conflicts", {}).get("main_conflict", "")
    secondary = story_bible.get("conflicts", {}).get("secondary_conflicts", [])
    active_threads: list[dict[str, Any]] = []
    if main_conflict:
        active_threads.append(
            {
                "thread_id": "main_conflict",
                "title": main_conflict,
                "status": "active",
                "priority": "P0",
                "introduced_chapter": 1,
                "last_updated_chapter": 1,
                "due_chapter": max(3, min(10, structure_map.get("target_chapters", 40) // 4)),
            },
        )

    for idx, item in enumerate(secondary, start=1):
        active_threads.append(
            {
                "thread_id": f"secondary_{idx:02d}",
                "title": item,
                "status": "active",
                "priority": "P1",
                "introduced_chapter": 1,
                "last_updated_chapter": 1,
                "due_chapter": max(4, 6 + idx * 3),
            },
        )

    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_chapter": 1,
        "author_intent": "",
        "current_focus": "",
        "character_states": character_states,
        "irreversible_events": [],
        "active_threads": active_threads,
        "thread_ledger": deepcopy(active_threads),
        "chapter_summaries": [],
        "continuation_anchor": {},
        "recent_progress": {},
        "foreshadows": [],
        "foreshadow_ledger": [],
        "state_deltas": [],
        "runtime_prompt_view": {},
    }


def _prepare_runtime_state(
    runtime_state: dict[str, Any] | None,
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
    chapter_no: int,
) -> dict[str, Any]:
    runtime = deepcopy(runtime_state) if runtime_state else seed_runtime_state(story_bible, structure_map)
    runtime.setdefault("character_states", [])
    runtime.setdefault("irreversible_events", [])
    runtime.setdefault("active_threads", [])
    runtime.setdefault("thread_ledger", [])
    runtime.setdefault("chapter_summaries", [])
    runtime.setdefault("continuation_anchor", {})
    runtime.setdefault("recent_progress", {})
    runtime.setdefault("foreshadows", [])
    runtime.setdefault("foreshadow_ledger", [])
    runtime.setdefault("state_deltas", [])
    runtime.setdefault("author_intent", "")
    runtime.setdefault("current_focus", "")
    runtime.setdefault("runtime_prompt_view", {})

    if not runtime["character_states"]:
        for ch in story_bible.get("characters", []):
            runtime["character_states"].append(
                {
                    "name": ch.get("name", "Unknown"),
                    "status": "active",
                    "survival_status": "active",
                    "current_state": "",
                    "position": "unknown",
                    "last_updated_chapter": 0,
                },
            )

    if not runtime["active_threads"] and runtime["thread_ledger"]:
        runtime["active_threads"] = deepcopy(runtime["thread_ledger"])

    if not runtime["active_threads"]:
        seeded = seed_runtime_state(story_bible, structure_map)
        runtime["active_threads"] = seeded["active_threads"]
        runtime["thread_ledger"] = seeded["thread_ledger"]

    _hydrate_continuity_artifacts(runtime, chapter_no)
    return runtime


def _hydrate_continuity_artifacts(runtime_state: dict[str, Any], chapter_no: int) -> None:
    book_root_raw = str(runtime_state.get("book_root", "")).strip()
    if not book_root_raw or chapter_no <= 1:
        return

    artifact = _read_latest_chapter_artifact(Path(book_root_raw), chapter_no)
    if not artifact:
        return

    summary = artifact.get("summary", "")
    chapter = _safe_int(artifact.get("chapter"), 0)
    tail = artifact.get("tail", "")

    if chapter > 0 and summary:
        existing = runtime_state.get("chapter_summaries", [])
        if not any(_safe_int(item.get("chapter"), 0) == chapter for item in existing if isinstance(item, dict)):
            existing.append({"chapter": chapter, "summary": summary})
            existing.sort(key=lambda item: _safe_int(item.get("chapter"), 0))

    if chapter > 0 and tail:
        existing_anchor = runtime_state.get("continuation_anchor", {})
        if not _has_continuation_anchor(existing_anchor):
            runtime_state["continuation_anchor"] = {
                "chapter": chapter,
                "tail": tail,
                "source": artifact.get("tail_source", ""),
            }

    if chapter > 0 and (summary or tail):
        existing_progress = runtime_state.get("recent_progress", {})
        if not _has_recent_progress(existing_progress):
            runtime_state["recent_progress"] = {
                "chapter": chapter,
                "summary": summary,
                "tail": tail,
            }


def _read_latest_chapter_artifact(book_root: Path, chapter_no: int) -> dict[str, Any]:
    chapters_dir = book_root / "chapters"
    if not chapters_dir.exists():
        return {}

    for prior_chapter in range(chapter_no - 1, 0, -1):
        chapter_dir = chapters_dir / f"{prior_chapter:04d}"
        if not chapter_dir.exists():
            continue
        summary = _read_chapter_summary(chapter_dir / "summary.json")
        tail, tail_source = _read_chapter_tail(chapter_dir)
        if summary or tail:
            return {
                "chapter": prior_chapter,
                "summary": summary,
                "tail": tail,
                "tail_source": tail_source,
            }
    return {}


def _read_chapter_summary(summary_path: Path) -> str:
    if not summary_path.exists():
        return ""
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    if isinstance(payload, dict):
        return str(payload.get("summary", "")).strip()
    return ""


def _read_chapter_tail(chapter_dir: Path) -> tuple[str, str]:
    for filename in ("draft.md", "package.json"):
        path = chapter_dir / filename
        if not path.exists():
            continue
        if filename == "draft.md":
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
        else:
            text = _read_package_draft(path)
        tail = _select_continuation_anchor(text)
        if tail:
            return tail, filename
    return "", ""


def _read_package_draft(package_path: Path) -> str:
    try:
        payload = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("draft_markdown", "") or payload.get("draft_markdown_raw", "")).strip()


def _select_continuation_anchor(text: str, max_chars: int = 220) -> str:
    normalized_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not normalized_lines:
        return ""
    candidate = normalized_lines[-1]
    if len(candidate) <= max_chars:
        return candidate
    return candidate[-max_chars:].lstrip()


def _has_continuation_anchor(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return _safe_int(value.get("chapter"), 0) > 0 and bool(str(value.get("tail", "")).strip())


def _has_recent_progress(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if _safe_int(value.get("chapter"), 0) <= 0:
        return False
    return bool(str(value.get("summary", "")).strip() or str(value.get("tail", "")).strip())


def _normalize_runtime_prompt_view_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_RUNTIME_PROMPT_VIEW_CONFIG)
    out.update(dict(cfg or {}))
    out["enabled"] = bool(out.get("enabled", True))
    out["shadow_mode"] = bool(out.get("shadow_mode", True))
    return out


def _resolve_runtime_prompt_view(runtime_state: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    view = runtime_state.get("runtime_prompt_view", {})
    if not isinstance(view, dict):
        return {}
    selected = view.get("selected", {})
    if not isinstance(selected, dict):
        return {}
    if not cfg.get("enabled", True):
        return {}
    return view


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
        "template_title": "Stage",
        "chapter_start": 1,
        "chapter_end": max(1, structure_map.get("target_chapters", 40)),
        "story_goal": "Push the core conflict forward.",
        "must_keep": [],
        "escalation_target": "Escalate pressure.",
    }


def _find_chapter_objective(structure_map: dict[str, Any], chapter_no: int) -> str:
    for item in structure_map.get("chapter_plan", []):
        if int(item.get("chapter", -1)) == chapter_no:
            return str(item.get("objective", "")).strip()
    return ""


def _build_tier_0_hard_facts(
    story_bible: dict[str, Any],
    runtime_state: dict[str, Any],
    stage_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    world_rules = story_bible.get("world", {}).get("rules", [])
    for idx, rule in enumerate(world_rules[:12], start=1):
        items.append(
            _entry(
                tier="tier_0",
                anchor=f"T0-WORLD-{idx:02d}",
                text=f"World rule (immutable): {rule}",
                priority=100,
                source="story_bible.world.rules",
            ),
        )

    for idx, ch in enumerate(runtime_state.get("character_states", [])[:24], start=1):
        name = ch.get("name", "Unknown")
        status = ch.get("status", "unknown")
        survival_status = ch.get("survival_status", "active")
        current_state = ch.get("current_state", "")
        pos = ch.get("position", "unknown")
        items.append(
            _entry(
                tier="tier_0",
                anchor=f"T0-CHAR-{idx:02d}",
                text=(
                    f"Character hard state: {name} | status={status} | survival={survival_status} "
                    f"| current_state={current_state} | position={pos}"
                ),
                priority=100,
                source="runtime_state.character_states",
            ),
        )

    for idx, ev in enumerate(runtime_state.get("irreversible_events", [])[:18], start=1):
        if isinstance(ev, str):
            text = ev
        else:
            text = f"{ev.get('title', 'event')} | effect={ev.get('effect', '')} | chapter={ev.get('chapter', '')}"
        items.append(
            _entry(
                tier="tier_0",
                anchor=f"T0-EVENT-{idx:02d}",
                text=f"Irreversible event: {text}",
                priority=110,
                source="runtime_state.irreversible_events",
            ),
        )

    main_conflict = story_bible.get("conflicts", {}).get("main_conflict", "")
    if main_conflict:
        items.append(
            _entry(
                tier="tier_0",
                anchor="T0-MAIN-CONFLICT",
                text=f"Main conflict baseline: {main_conflict}",
                priority=120,
                source="story_bible.conflicts.main_conflict",
            ),
        )

    items.append(
        _entry(
            tier="tier_0",
            anchor="T0-STAGE-GOAL",
            text=(
                "Current stage target baseline: "
                f"{stage_contract.get('story_goal', '')} "
                f"(stage={stage_contract.get('stage_id', '')})"
            ),
            priority=130,
            source="structure_map.stage_contracts",
        ),
    )

    return items


def _build_tier_1_stage_contract(
    stage_contract: dict[str, Any],
    chapter_objective: str,
    chapter_no: int,
) -> list[dict[str, Any]]:
    guardrails = [
        "Do not consume future climax early.",
        "Do not break stage order.",
        "Chapter objective must produce a visible progression.",
    ]
    items: list[dict[str, Any]] = [
        _entry(
            tier="tier_1",
            anchor="T1-STAGE-RANGE",
            text=(
                f"Stage contract: {stage_contract.get('stage_id', '')} | "
                f"chapter_range={stage_contract.get('chapter_start', '')}-{stage_contract.get('chapter_end', '')} | "
                f"template_anchor={stage_contract.get('template_title', '')}"
            ),
            priority=200,
            source="structure_map.stage_contracts",
        ),
        _entry(
            tier="tier_1",
            anchor="T1-STAGE-GOAL",
            text=f"Stage story goal: {stage_contract.get('story_goal', '')}",
            priority=205,
            source="structure_map.stage_contracts.story_goal",
        ),
    ]

    if chapter_objective:
        items.append(
            _entry(
                tier="tier_1",
                anchor="T1-CHAPTER-OBJECTIVE",
                text=f"Chapter {chapter_no} objective: {chapter_objective}",
                priority=210,
                source="structure_map.chapter_plan",
            ),
        )

    for idx, keep in enumerate(stage_contract.get("must_keep", [])[:8], start=1):
        items.append(
            _entry(
                tier="tier_1",
                anchor=f"T1-MUST-KEEP-{idx:02d}",
                text=f"Must-keep contract: {keep}",
                priority=215 - idx,
                source="structure_map.stage_contracts.must_keep",
            ),
        )

    escalation = stage_contract.get("escalation_target", "")
    if escalation:
        items.append(
            _entry(
                tier="tier_1",
                anchor="T1-ESCALATION",
                text=f"Escalation target: {escalation}",
                priority=220,
                source="structure_map.stage_contracts.escalation_target",
            ),
        )

    for idx, rule in enumerate(guardrails, start=1):
        items.append(
            _entry(
                tier="tier_1",
                anchor=f"T1-GUARD-{idx:02d}",
                text=f"Guardrail: {rule}",
                priority=190 - idx,
                source="context_engine.guardrails",
            ),
        )
    return items


def _build_tier_2_active_threads(
    story_bible: dict[str, Any],
    runtime_state: dict[str, Any],
    chapter_no: int,
    runtime_prompt_view: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    selected = runtime_prompt_view.get("selected", {}) if isinstance(runtime_prompt_view, dict) else {}
    selected_threads = selected.get("active_threads", []) if isinstance(selected, dict) else []
    selected_foreshadows = selected.get("foreshadows_due", []) if isinstance(selected, dict) else []

    if isinstance(selected_threads, list) and selected_threads:
        threads = _normalize_threads(selected_threads, [])
        thread_source = "runtime_prompt_view.selected.active_threads"
    else:
        threads = _normalize_threads(runtime_state.get("active_threads", []), runtime_state.get("thread_ledger", []))
        thread_source = "runtime_state.active_threads"
    entries: list[dict[str, Any]] = []

    for idx, thread in enumerate(threads, start=1):
        status = thread.get("status", "active").lower()
        due = int(thread.get("due_chapter", max(chapter_no + 2, 3)))
        urgency = _thread_urgency(status, due, chapter_no)
        entries.append(
            _entry(
                tier="tier_2",
                anchor=f"T2-THREAD-{idx:02d}",
                text=(
                    f"Thread: {thread.get('title', '')} | status={status} | "
                    f"due_chapter={due} | latest_note={thread.get('note', '')}"
                ),
                priority=urgency,
                source=thread_source,
            ),
        )

    foreshadows_source = "runtime_state.foreshadows"
    foreshadows: list[Any]
    if isinstance(selected_foreshadows, list) and selected_foreshadows:
        foreshadows = selected_foreshadows
        foreshadows_source = "runtime_prompt_view.selected.foreshadows_due"
    else:
        foreshadows = runtime_state.get("foreshadows", [])[:10]
    for idx, f in enumerate(foreshadows, start=1):
        if isinstance(f, str):
            text = f
            due = chapter_no + 3
            status = "active"
        else:
            text = f.get("description", "")
            due = int(f.get("due_chapter", chapter_no + 3))
            status = str(f.get("status", "active"))
        urgency = _thread_urgency(status, due, chapter_no)
        entries.append(
            _entry(
                tier="tier_2",
                anchor=f"T2-FORESHADOW-{idx:02d}",
                text=f"Foreshadow thread: {text} | status={status} | due_chapter={due}",
                priority=urgency,
                source=foreshadows_source,
            ),
        )

    intent = runtime_state.get("author_intent", "").strip()
    focus = runtime_state.get("current_focus", "").strip()
    if intent:
        entries.append(
            _entry(
                tier="tier_2",
                anchor="T2-AUTHOR-INTENT",
                text=f"Author intent (must converge): {intent}",
                priority=160,
                source="runtime_state.author_intent",
            ),
        )
    if focus:
        entries.append(
            _entry(
                tier="tier_2",
                anchor="T2-CURRENT-FOCUS",
                text=f"Current focus (near-term): {focus}",
                priority=150,
                source="runtime_state.current_focus",
            ),
        )

    if not entries:
        main_conflict = story_bible.get("conflicts", {}).get("main_conflict", "")
        if main_conflict:
            entries.append(
                _entry(
                    tier="tier_2",
                    anchor="T2-FALLBACK-MAIN",
                    text=f"Fallback active thread: {main_conflict}",
                    priority=140,
                    source="story_bible.conflicts.main_conflict",
                ),
            )

    return sorted(entries, key=lambda x: (-int(x["priority"]), x["anchor"]))


def _build_tier_3_retrieval_evidence(
    template_dna: dict[str, Any],
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
    runtime_state: dict[str, Any],
    chapter_no: int,
    stage_contract: dict[str, Any],
    tier2: list[dict[str, Any]],
    runtime_prompt_view: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    selected = runtime_prompt_view.get("selected", {}) if isinstance(runtime_prompt_view, dict) else {}
    digests = runtime_prompt_view.get("digests", {}) if isinstance(runtime_prompt_view, dict) else {}
    query_digest = ""
    if isinstance(digests, dict):
        query_digest = " ".join(
            str(digests.get(k, "")).strip()
            for k in (
                "recent_plot_digest",
                "core_conflict_digest",
                "due_foreshadow_digest",
                "continuity_risk_digest",
            )
            if str(digests.get(k, "")).strip()
        )
    query = " ".join(
        [
            str(stage_contract.get("story_goal", "")),
            str(runtime_state.get("author_intent", "")),
            str(runtime_state.get("current_focus", "")),
            query_digest,
            " ".join(item.get("text", "") for item in tier2[:8]),
        ],
    )
    query_tokens = _tokenize(query)

    candidates: list[dict[str, Any]] = []
    chapter_summary_source = "runtime_state.chapter_summaries"
    chapter_summaries: list[Any] = runtime_state.get("chapter_summaries", [])
    if isinstance(selected, dict):
        selected_summaries = selected.get("recent_chapter_summaries", [])
        if isinstance(selected_summaries, list) and selected_summaries:
            chapter_summaries = selected_summaries
            chapter_summary_source = "runtime_prompt_view.selected.recent_chapter_summaries"
    for rec in chapter_summaries:
        chapter = int(rec.get("chapter", 0)) if isinstance(rec, dict) else 0
        summary = rec.get("summary", "") if isinstance(rec, dict) else str(rec)
        candidates.append(
            {
                "anchor": f"T3-CHSUM-{chapter:03d}",
                "text": f"Chapter {chapter} summary evidence: {summary}",
                "source": chapter_summary_source,
                "chapter": chapter,
            },
        )

    continuation_anchor = runtime_state.get("continuation_anchor", {})
    if isinstance(continuation_anchor, dict):
        anchor_chapter = _safe_int(continuation_anchor.get("chapter"), 0)
        anchor_tail = str(continuation_anchor.get("tail", "")).strip()
        if anchor_chapter > 0 and anchor_tail:
            candidates.append(
                {
                    "anchor": f"T3-CONT-{anchor_chapter:03d}",
                    "text": f"Continuation anchor from chapter {anchor_chapter}: {anchor_tail}",
                    "source": "runtime_state.continuation_anchor",
                    "chapter": anchor_chapter,
                },
            )

    recent_progress = runtime_state.get("recent_progress", {})
    if isinstance(recent_progress, dict):
        progress_chapter = _safe_int(recent_progress.get("chapter"), 0)
        progress_summary = str(recent_progress.get("summary", "")).strip()
        if progress_chapter > 0 and progress_summary:
            candidates.append(
                {
                    "anchor": f"T3-PROGRESS-{progress_chapter:03d}",
                    "text": f"Recent progress from chapter {progress_chapter}: {progress_summary}",
                    "source": "runtime_state.recent_progress",
                    "chapter": progress_chapter,
                },
            )

    if isinstance(digests, dict):
        for key, label in (
            ("recent_plot_digest", "Recent plot digest evidence"),
            ("core_conflict_digest", "Core conflict digest evidence"),
            ("due_foreshadow_digest", "Due foreshadow digest evidence"),
            ("continuity_risk_digest", "Continuity risk digest evidence"),
        ):
            text = str(digests.get(key, "")).strip()
            if not text:
                continue
            candidates.append(
                {
                    "anchor": f"T3-DIGEST-{key.upper()}",
                    "text": f"{label}: {text}",
                    "source": "runtime_prompt_view.digests",
                    "chapter": chapter_no,
                },
            )

    for item in structure_map.get("chapter_plan", []):
        chapter = int(item.get("chapter", 0))
        if chapter >= chapter_no:
            continue
        objective = str(item.get("objective", "")).strip()
        if not objective:
            continue
        candidates.append(
            {
                "anchor": f"T3-PLAN-{chapter:03d}",
                "text": f"Prior plan objective from chapter {chapter}: {objective}",
                "source": "structure_map.chapter_plan",
                "chapter": chapter,
            },
        )

    for idx, p in enumerate(template_dna.get("principles", [])[:10], start=1):
        detail = p.get("detail", "") if isinstance(p, dict) else str(p)
        if detail:
            candidates.append(
                {
                    "anchor": f"T3-PRINCIPLE-{idx:02d}",
                    "text": f"Template principle evidence: {detail}",
                    "source": "template_dna.principles",
                    "chapter": 0,
                },
            )

    for idx, d in enumerate(template_dna.get("dialogue_patterns", [])[:8], start=1):
        if isinstance(d, dict):
            text = f"{d.get('name', '')}: {d.get('description', '')}"
        else:
            text = str(d)
        if text.strip():
            candidates.append(
                {
                    "anchor": f"T3-DIALOG-{idx:02d}",
                    "text": f"Dialogue style evidence: {text}",
                    "source": "template_dna.dialogue_patterns",
                    "chapter": 0,
                },
            )

    premise = story_bible.get("premise", {}).get("logline", "")
    if premise:
        candidates.append(
            {
                "anchor": "T3-PREMISE",
                "text": f"Original premise evidence: {premise}",
                "source": "story_bible.premise.logline",
                "chapter": 0,
            },
        )

    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        score = _evidence_score(query_tokens, candidate["text"], chapter_no, int(candidate.get("chapter", 0)))
        scored.append(
            _entry(
                tier="tier_3",
                anchor=candidate["anchor"],
                text=candidate["text"],
                priority=score,
                source=candidate["source"],
            ),
        )

    scored.sort(key=lambda x: (-int(x["priority"]), x["anchor"]))
    return scored[:18]


def _normalize_threads(active_threads: list[Any], thread_ledger: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    source = active_threads or thread_ledger
    for item in source:
        if isinstance(item, str):
            normalized.append({"title": item, "status": "active", "priority": "P1", "due_chapter": 9999, "note": ""})
            continue
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "title": str(item.get("title", item.get("thread", item.get("thread_id", "")))).strip(),
                "status": str(item.get("status", "active")).strip().lower(),
                "priority": str(item.get("priority", "P1")).strip(),
                "due_chapter": _safe_int(item.get("due_chapter"), 9999),
                "note": str(item.get("note", item.get("latest_note", ""))).strip(),
            },
        )
    return [x for x in normalized if x["title"]]


def _thread_urgency(status: str, due_chapter: int, chapter_no: int) -> int:
    status_base = {
        "overdue": 170,
        "due": 155,
        "active": 135,
        "paused": 100,
        "resolved": 85,
    }.get(status, 120)
    delta = due_chapter - chapter_no
    if delta <= 0:
        return status_base + 20
    if delta <= 2:
        return status_base + 10
    if delta <= 5:
        return status_base + 5
    return status_base


def _evidence_score(query_tokens: set[str], text: str, current_chapter: int, chapter: int) -> int:
    overlap = len(query_tokens.intersection(_tokenize(text)))
    if chapter > 0:
        recency = max(0, 20 - min(20, abs(current_chapter - chapter)))
    else:
        recency = 6
    return overlap * 3 + recency


def _tokenize(text: str) -> set[str]:
    text = text or ""
    words = re.findall(r"[A-Za-z0-9_]+", text.lower())
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    tokens = set(words)
    tokens.update(cjk_chars)
    return tokens


def _apply_budget_strategy(
    tier0: list[dict[str, Any]],
    tier1: list[dict[str, Any]],
    tier2: list[dict[str, Any]],
    tier3: list[dict[str, Any]],
    token_budget: int,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    work = {
        "tier_0": deepcopy(tier0),
        "tier_1": deepcopy(tier1),
        "tier_2": deepcopy(tier2),
        "tier_3": deepcopy(tier3),
    }
    compression_log: list[dict[str, Any]] = []

    # Optional tiers are compressed first: tier_3 then tier_2.
    while _estimate_total_tokens(work["tier_0"], work["tier_1"], work["tier_2"], work["tier_3"]) > token_budget:
        if _compress_or_drop_optional(work["tier_3"], "tier_3", compression_log):
            continue
        if _compress_or_drop_optional(work["tier_2"], "tier_2", compression_log):
            continue
        break

    # Mandatory tiers can be summarized but never dropped.
    if _estimate_total_tokens(work["tier_0"], work["tier_1"], work["tier_2"], work["tier_3"]) > token_budget:
        _summarize_mandatory_tiers(work, token_budget, compression_log)

    return work, compression_log


def _compress_or_drop_optional(
    items: list[dict[str, Any]],
    tier_name: str,
    compression_log: list[dict[str, Any]],
) -> bool:
    if not items:
        return False

    # Step 1: try summarizing the longest item.
    target = max(items, key=lambda x: len(x["text"]))
    before = target["text"]
    shrunk = _compress_text(before, 0.72, min_chars=48)
    if shrunk != before:
        target["text"] = shrunk
        compression_log.append(
            {
                "action": "summarize",
                "tier": tier_name,
                "anchor": target["anchor"],
                "before_chars": len(before),
                "after_chars": len(shrunk),
            },
        )
        return True

    # Step 2: if no longer compressible, drop the lowest-priority item.
    drop_idx = min(range(len(items)), key=lambda idx: int(items[idx]["priority"]))
    dropped = items.pop(drop_idx)
    compression_log.append(
        {
            "action": "drop_optional",
            "tier": tier_name,
            "anchor": dropped["anchor"],
            "reason": "optional tier over budget and item at minimum compression",
        },
    )
    return True


def _summarize_mandatory_tiers(
    work: dict[str, list[dict[str, Any]]],
    token_budget: int,
    compression_log: list[dict[str, Any]],
) -> None:
    passes = [0.75, 0.62, 0.50, 0.40, 0.32]
    for ratio in passes:
        if _estimate_total_tokens(work["tier_0"], work["tier_1"], work["tier_2"], work["tier_3"]) <= token_budget:
            return
        for tier_name in ("tier_0", "tier_1"):
            for item in work[tier_name]:
                before = item["text"]
                after = _compress_text(before, ratio, min_chars=38)
                if after != before:
                    item["text"] = after
                    compression_log.append(
                        {
                            "action": "summarize_mandatory",
                            "tier": tier_name,
                            "anchor": item["anchor"],
                            "ratio": ratio,
                            "before_chars": len(before),
                            "after_chars": len(after),
                        },
                    )


def _compress_text(text: str, ratio: float, min_chars: int) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return cleaned
    target_len = max(min_chars, int(math.floor(len(cleaned) * ratio)))
    if target_len >= len(cleaned):
        return cleaned

    # Keep first sentence-ish chunk if possible, then trim.
    parts = re.split(r"[。；;.!?]+", cleaned)
    candidate = parts[0].strip() if parts and parts[0].strip() else cleaned
    if len(candidate) > target_len:
        candidate = cleaned
    if len(candidate) <= target_len:
        return candidate if len(candidate) >= min_chars else _ellipsis(cleaned, target_len)
    return _ellipsis(cleaned, target_len)


def _ellipsis(text: str, target_len: int) -> str:
    if target_len <= 1:
        return "…"
    return text[: max(1, target_len - 1)].rstrip() + "…"


def _estimate_total_tokens(
    tier0: list[dict[str, Any]],
    tier1: list[dict[str, Any]],
    tier2: list[dict[str, Any]],
    tier3: list[dict[str, Any]],
) -> int:
    return _estimate_items_tokens(tier0) + _estimate_items_tokens(tier1) + _estimate_items_tokens(tier2) + _estimate_items_tokens(tier3)


def _estimate_items_tokens(items: list[dict[str, Any]]) -> int:
    total = 0
    for item in items:
        total += _estimate_text_tokens(_entry_to_line(item))
    return total


def _estimate_text_tokens(text: str) -> int:
    ascii_words = len(re.findall(r"[A-Za-z0-9_]+", text))
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    punct = len(re.findall(r"[^\w\s\u4e00-\u9fff]", text))
    return ascii_words + math.ceil(cjk_chars * 0.70) + math.ceil(punct * 0.20) + 2


def _entry(
    tier: str,
    anchor: str,
    text: str,
    priority: int,
    source: str,
) -> dict[str, Any]:
    return {
        "tier": tier,
        "anchor": anchor,
        "text": text.strip(),
        "priority": int(priority),
        "source": source,
    }


def _entry_to_line(item: dict[str, Any]) -> str:
    return f"[{item['anchor']}] {item['text']}"


def _render_tier_block(items: list[dict[str, Any]]) -> str:
    if not items:
        return "(empty)"
    return "\n".join(f"- {_entry_to_line(item)}" for item in items)


def _render_full_context(packed: dict[str, list[dict[str, Any]]]) -> str:
    blocks = [
        "## Tier-0 Hard Facts",
        _render_tier_block(packed["tier_0"]),
        "",
        "## Tier-1 Stage Contract",
        _render_tier_block(packed["tier_1"]),
        "",
        "## Tier-2 Active Threads",
        _render_tier_block(packed["tier_2"]),
        "",
        "## Tier-3 Retrieval Evidence",
        _render_tier_block(packed["tier_3"]),
    ]
    return "\n".join(blocks).strip()


def _render_budget_report_markdown(bundle: dict[str, Any]) -> str:
    tiers = bundle["tiers"]
    budget = bundle["budget_report"]
    prompt_view_report = bundle.get("prompt_view_report", {}) if isinstance(bundle, dict) else {}
    prompt_view_stats = prompt_view_report.get("stats", {}) if isinstance(prompt_view_report, dict) else {}
    lines = [
        f"# T4 Context Report - Chapter {bundle['chapter']}",
        "",
        "## Budget",
        f"- Budget tokens: {budget['token_budget']}",
        f"- Estimated tokens: {budget['estimated_tokens']}",
        f"- Budget met: {budget['budget_met']}",
        "",
        "## Invariants",
        f"- Tier-0 dropped: {bundle['invariants']['tier_0_dropped']}",
        f"- Tier-1 dropped: {bundle['invariants']['tier_1_dropped']}",
        f"- Mandatory non-dropping active: {bundle['invariants']['mandatory_tiers_never_dropped']}",
        "",
        "## Tier Stats",
        f"- Tier-0 items: {len(tiers['tier_0_hard_facts']['items'])}",
        f"- Tier-1 items: {len(tiers['tier_1_stage_contract']['items'])}",
        f"- Tier-2 items: {len(tiers['tier_2_active_threads']['items'])}",
        f"- Tier-3 items: {len(tiers['tier_3_retrieval_evidence']['items'])}",
        "",
        "## Prompt View",
        f"- enabled: {prompt_view_report.get('enabled', False)}",
        f"- shadow_mode: {prompt_view_report.get('shadow_mode', True)}",
        f"- source_mode: {prompt_view_report.get('source_mode', 'runtime_state_raw')}",
        f"- raw_summary_count: {prompt_view_stats.get('raw_summary_count', 0)}",
        f"- selected_summary_count: {prompt_view_stats.get('selected_summary_count', 0)}",
        f"- raw_thread_count: {prompt_view_stats.get('raw_thread_count', 0)}",
        f"- selected_thread_count: {prompt_view_stats.get('selected_thread_count', 0)}",
        f"- raw_foreshadow_count: {prompt_view_stats.get('raw_foreshadow_count', 0)}",
        f"- selected_foreshadow_count: {prompt_view_stats.get('selected_foreshadow_count', 0)}",
        "",
        "## Compression Log",
    ]
    if bundle["compression_log"]:
        for item in bundle["compression_log"]:
            lines.append(f"- {item}")
    else:
        lines.append("- No compression needed.")
    lines.append("")
    return "\n".join(lines)


def _safe_int(raw: Any, default: int) -> int:
    if isinstance(raw, int):
        return raw
    text = str(raw or "")
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return default
    try:
        return int(digits)
    except ValueError:
        return default

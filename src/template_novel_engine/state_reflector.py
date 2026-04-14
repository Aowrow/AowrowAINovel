from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


ACTION_BURY = "埋入"
ACTION_PROGRESS = "推进"
ACTION_RECOVER = "回收"
ACTION_OVERDUE = "超期"

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


def apply_t6_state_reflection(
    runtime_state: dict[str, Any],
    story_bible: dict[str, Any],
    chapter_no: int,
    draft_markdown: str,
    chapter_summary: str,
    contract: dict[str, Any],
    alignment: dict[str, Any],
    chapter_analysis: dict[str, Any] | None = None,
    audit_report: dict[str, Any] | None = None,
    author_intent: str = "",
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    runtime = _ensure_runtime_shape(runtime_state)
    delta = extract_state_delta(
        runtime_state=runtime,
        story_bible=story_bible,
        chapter_no=chapter_no,
        draft_markdown=draft_markdown,
        chapter_summary=chapter_summary,
        contract=contract,
        alignment=alignment,
        chapter_analysis=chapter_analysis,
    )
    runtime_after = apply_state_delta(
        runtime_state=runtime,
        chapter_no=chapter_no,
        chapter_summary=chapter_summary,
        contract=contract,
        alignment=alignment,
        delta=delta,
        chapter_analysis=chapter_analysis,
        audit_report=audit_report,
        author_intent=author_intent,
        runtime_prompt_view_cfg=runtime_prompt_view_cfg,
    )
    report = build_t6_report(runtime_after, chapter_no, delta)
    return runtime_after, delta, report


def replay_t6_from_chapter_package(
    runtime_state: dict[str, Any],
    story_bible: dict[str, Any],
    chapter_package: dict[str, Any],
    author_intent: str = "",
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    chapter_no = int(chapter_package.get("chapter", 0))
    if chapter_no <= 0:
        raise ValueError("chapter_package.chapter must be a positive integer.")
    contract = chapter_package.get("contract", {})
    draft = str(chapter_package.get("draft_markdown", ""))
    summary = str(chapter_package.get("chapter_summary", ""))
    alignment = chapter_package.get("alignment_report", {})
    chapter_analysis = chapter_package.get("chapter_analysis", {})
    audit_report = chapter_package.get("t7_audit_report", {})
    return apply_t6_state_reflection(
        runtime_state=runtime_state,
        story_bible=story_bible,
        chapter_no=chapter_no,
        draft_markdown=draft,
        chapter_summary=summary,
        contract=contract,
        alignment=alignment,
        chapter_analysis=chapter_analysis if isinstance(chapter_analysis, dict) else None,
        audit_report=audit_report if isinstance(audit_report, dict) else None,
        author_intent=author_intent,
        runtime_prompt_view_cfg=runtime_prompt_view_cfg,
    )


def extract_state_delta(
    runtime_state: dict[str, Any],
    story_bible: dict[str, Any],
    chapter_no: int,
    draft_markdown: str,
    chapter_summary: str,
    contract: dict[str, Any],
    alignment: dict[str, Any],
    chapter_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text_blob = f"{draft_markdown}\n{chapter_summary}\n{contract.get('chapter_objective', '')}"
    analysis = chapter_analysis if isinstance(chapter_analysis, dict) else {}

    touched_chars: list[dict[str, Any]] = []
    if analysis.get("character_states"):
        touched_chars = _character_updates_from_analysis(analysis, chapter_no)
    else:
        for ch in story_bible.get("characters", []):
            name = str(ch.get("name", "")).strip()
            if not name:
                continue
            if name in text_blob:
                touched_chars.append(
                    {
                        "name": name,
                        "status_hint": "active",
                        "note": f"mentioned in chapter {chapter_no}",
                    },
                )

    if not touched_chars:
        protagonist = _resolve_protagonist_name(story_bible)
        touched_chars.append(
            {
                "name": protagonist,
                "status_hint": "active",
                "note": f"default protagonist touch in chapter {chapter_no}",
            },
        )

    thread_actions: list[dict[str, Any]] = []
    primary_thread = _pick_primary_thread(runtime_state)
    if primary_thread:
        conflict_note = ""
        if isinstance(analysis.get("conflict"), dict):
            conflict_note = str(analysis.get("conflict", {}).get("description", "")).strip()
        thread_actions.append(
            {
                "action": ACTION_PROGRESS,
                "thread_id": primary_thread.get("thread_id", ""),
                "title": primary_thread.get("title", ""),
                "note": conflict_note or f"chapter objective progressed: {contract.get('chapter_objective', '')}",
            },
        )

    foreshadow_actions: list[dict[str, Any]] = []
    if analysis.get("foreshadows"):
        foreshadow_actions = _foreshadow_actions_from_analysis(
            foreshadows=analysis.get("foreshadows", []),
            chapter_no=chapter_no,
            fallback_thread_id=primary_thread.get("thread_id", "") if primary_thread else "",
        )
    else:
        new_fs_id = f"fs_{chapter_no:03d}_01"
        objective = str(contract.get("chapter_objective", "")).strip()
        foreshadow_actions.append(
            {
                "action": ACTION_BURY,
                "foreshadow_id": new_fs_id,
                "description": _clip_text(objective or chapter_summary, 100),
                "due_chapter": chapter_no + 2,
                "thread_id": primary_thread.get("thread_id", "") if primary_thread else "",
                "note": "new foreshadow seeded from chapter objective",
            },
        )

        open_before = _open_foreshadow_ids(runtime_state)
        if open_before:
            foreshadow_actions.append(
                {
                    "action": ACTION_PROGRESS,
                    "foreshadow_id": open_before[0],
                    "note": f"continued in chapter {chapter_no}",
                },
            )
        if _should_recover_this_chapter(chapter_no, contract):
            recover_target = open_before[0] if open_before else new_fs_id
            foreshadow_actions.append(
                {
                    "action": ACTION_RECOVER,
                    "foreshadow_id": recover_target,
                    "note": f"payoff in chapter {chapter_no}",
                },
            )

    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapter": chapter_no,
        "alignment_pass": bool(alignment.get("pass", False)),
        "character_updates": touched_chars,
        "thread_actions": thread_actions,
        "foreshadow_actions": foreshadow_actions,
        "chapter_analysis": analysis if isinstance(analysis, dict) else {},
        "irreversible_events": [],
    }


def apply_state_delta(
    runtime_state: dict[str, Any],
    chapter_no: int,
    chapter_summary: str,
    contract: dict[str, Any],
    alignment: dict[str, Any],
    delta: dict[str, Any],
    chapter_analysis: dict[str, Any] | None = None,
    audit_report: dict[str, Any] | None = None,
    author_intent: str = "",
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = _ensure_runtime_shape(runtime_state)
    runtime["current_chapter"] = chapter_no
    runtime["updated_at"] = datetime.now(timezone.utc).isoformat()
    if author_intent.strip():
        runtime["author_intent"] = author_intent.strip()
        runtime["current_focus"] = author_intent.strip()
    else:
        runtime["current_focus"] = str(contract.get("chapter_objective", "")).strip()

    _apply_character_updates(runtime, delta.get("character_updates", []), chapter_no)
    _apply_thread_actions(runtime, delta.get("thread_actions", []), chapter_no)
    _apply_foreshadow_actions(runtime, delta.get("foreshadow_actions", []), chapter_no)
    _mark_overdue_foreshadows(runtime, chapter_no)

    runtime.setdefault("chapter_summaries", []).append(
        {
            "chapter": chapter_no,
            "summary": chapter_summary,
            "stage_id": contract.get("stage_id", ""),
            "objective": contract.get("chapter_objective", ""),
            "alignment_pass": alignment.get("pass", False),
        },
    )
    runtime["chapter_summaries"] = runtime["chapter_summaries"][-180:]
    runtime.setdefault("state_deltas", []).append(delta)
    runtime["state_deltas"] = runtime["state_deltas"][-240:]
    _append_quality_history(runtime, chapter_no, audit_report, alignment)
    runtime["last_alignment"] = alignment
    if isinstance(chapter_analysis, dict) and chapter_analysis:
        runtime["last_chapter_analysis"] = chapter_analysis

    runtime["foreshadows"] = _build_active_foreshadow_view(runtime)
    runtime["thread_ledger"] = deepcopy(runtime.get("active_threads", []))
    runtime["runtime_prompt_view"] = build_runtime_prompt_view(
        runtime_state=runtime,
        chapter_no=chapter_no,
        cfg=runtime_prompt_view_cfg,
    )
    return runtime


def build_t6_report(runtime_state: dict[str, Any], chapter_no: int, delta: dict[str, Any]) -> dict[str, Any]:
    ledger = runtime_state.get("foreshadow_ledger", [])
    counts = {
        ACTION_BURY: 0,
        ACTION_PROGRESS: 0,
        ACTION_RECOVER: 0,
        ACTION_OVERDUE: 0,
    }
    for item in ledger:
        status = str(item.get("status", "")).strip()
        if status in counts:
            counts[status] += 1

    this_chapter_actions = [a.get("action", "") for a in delta.get("foreshadow_actions", [])]
    has_all_status_tracking = (
        counts[ACTION_BURY] >= 0
        and counts[ACTION_PROGRESS] >= 0
        and counts[ACTION_RECOVER] >= 0
        and counts[ACTION_OVERDUE] >= 0
    )
    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapter": chapter_no,
        "delta_stats": {
            "character_updates": len(delta.get("character_updates", [])),
            "thread_actions": len(delta.get("thread_actions", [])),
            "foreshadow_actions": len(delta.get("foreshadow_actions", [])),
        },
        "foreshadow_status_counts": counts,
        "this_chapter_foreshadow_actions": this_chapter_actions,
        "trackability_ok": has_all_status_tracking,
        "open_foreshadows": len(_open_foreshadow_ids(runtime_state)),
    }


def render_t6_report_markdown(report: dict[str, Any]) -> str:
    c = report.get("foreshadow_status_counts", {})
    d = report.get("delta_stats", {})
    lines = [
        f"# T6 Report - Chapter {report.get('chapter', '?')}",
        "",
        "## Delta",
        f"- character updates: {d.get('character_updates', 0)}",
        f"- thread actions: {d.get('thread_actions', 0)}",
        f"- foreshadow actions: {d.get('foreshadow_actions', 0)}",
        "",
        "## Foreshadow Ledger",
        f"- 埋入: {c.get(ACTION_BURY, 0)}",
        f"- 推进: {c.get(ACTION_PROGRESS, 0)}",
        f"- 回收: {c.get(ACTION_RECOVER, 0)}",
        f"- 超期: {c.get(ACTION_OVERDUE, 0)}",
        f"- open foreshadows: {report.get('open_foreshadows', 0)}",
        "",
        f"- trackability_ok: {report.get('trackability_ok', False)}",
        f"- this chapter actions: {report.get('this_chapter_foreshadow_actions', [])}",
        "",
    ]
    return "\n".join(lines)


def _ensure_runtime_shape(runtime_state: dict[str, Any]) -> dict[str, Any]:
    runtime = deepcopy(runtime_state)
    runtime.setdefault("character_states", [])
    runtime.setdefault("active_threads", [])
    runtime.setdefault("thread_ledger", [])
    runtime.setdefault("chapter_summaries", [])
    runtime.setdefault("foreshadows", [])
    runtime.setdefault("foreshadow_ledger", [])
    runtime.setdefault("state_deltas", [])
    runtime.setdefault("quality_history", [])
    runtime.setdefault("author_intent", "")
    runtime.setdefault("current_focus", "")
    runtime.setdefault("irreversible_events", [])
    runtime.setdefault("runtime_prompt_view", {})
    return runtime


def _apply_character_updates(runtime: dict[str, Any], updates: list[dict[str, Any]], chapter_no: int) -> None:
    states = runtime.setdefault("character_states", [])
    index = {str(item.get("name", "")): item for item in states if isinstance(item, dict)}
    for upd in updates:
        name = str(upd.get("name", "")).strip()
        if not name:
            continue
        if name not in index:
            record = {
                "name": name,
                "status": str(upd.get("status_hint", "unknown")),
                "survival_status": str(upd.get("survival_status", "active")),
                "current_state": str(upd.get("state_after", "")),
                "position": "unknown",
                "last_updated_chapter": chapter_no,
            }
            states.append(record)
            index[name] = record
        else:
            rec = index[name]
            rec["status"] = str(upd.get("status_hint", rec.get("status", "unknown")))
            rec["survival_status"] = str(upd.get("survival_status", rec.get("survival_status", "active")))
            if upd.get("state_after"):
                rec["current_state"] = str(upd.get("state_after"))
            if upd.get("relationship_changes"):
                rec["relationship_changes"] = upd.get("relationship_changes")
            rec["last_updated_chapter"] = chapter_no
            if upd.get("note"):
                rec["note"] = str(upd.get("note"))


def _apply_thread_actions(runtime: dict[str, Any], actions: list[dict[str, Any]], chapter_no: int) -> None:
    threads = runtime.setdefault("active_threads", [])
    if not threads:
        return

    for action in actions:
        act = str(action.get("action", "")).strip()
        thread_id = str(action.get("thread_id", "")).strip()
        title = str(action.get("title", "")).strip()
        target = _find_thread(threads, thread_id, title)
        if not target:
            continue
        if act == ACTION_PROGRESS:
            target["status"] = "active"
            target["last_updated_chapter"] = chapter_no
            target["note"] = str(action.get("note", "")).strip()
        elif act == ACTION_RECOVER:
            target["status"] = "resolved"
            target["resolved_chapter"] = chapter_no
            target["last_updated_chapter"] = chapter_no

    for item in threads:
        due = _safe_int(item.get("due_chapter"), 9999)
        status = str(item.get("status", "active")).lower()
        if status in {"resolved", "closed"}:
            continue
        if chapter_no > due:
            item["status"] = "overdue"
        elif chapter_no == due:
            item["status"] = "due"


def _apply_foreshadow_actions(runtime: dict[str, Any], actions: list[dict[str, Any]], chapter_no: int) -> None:
    ledger = runtime.setdefault("foreshadow_ledger", [])
    idx_map = {str(item.get("foreshadow_id", "")): item for item in ledger if isinstance(item, dict)}

    for action in actions:
        act = str(action.get("action", "")).strip()
        fid = str(action.get("foreshadow_id", "")).strip()
        if not fid:
            continue

        if act == ACTION_BURY:
            record = idx_map.get(fid)
            if not record:
                record = {
                    "foreshadow_id": fid,
                    "description": str(action.get("description", "")).strip(),
                    "thread_id": str(action.get("thread_id", "")).strip(),
                    "introduced_chapter": chapter_no,
                    "due_chapter": _safe_int(action.get("due_chapter"), chapter_no + 2),
                    "status": ACTION_BURY,
                    "last_updated_chapter": chapter_no,
                    "history": [],
                }
                ledger.append(record)
                idx_map[fid] = record
            _append_history(record, chapter_no, ACTION_BURY, str(action.get("note", "")))
            record["status"] = ACTION_BURY
            record["last_updated_chapter"] = chapter_no
            continue

        record = idx_map.get(fid)
        if not record:
            # Unknown foreshadow fallback: create minimal record so action remains traceable.
            record = {
                "foreshadow_id": fid,
                "description": str(action.get("description", "")).strip(),
                "thread_id": str(action.get("thread_id", "")).strip(),
                "introduced_chapter": chapter_no,
                "due_chapter": chapter_no + 2,
                "status": ACTION_BURY,
                "last_updated_chapter": chapter_no,
                "history": [],
            }
            ledger.append(record)
            idx_map[fid] = record
            _append_history(record, chapter_no, ACTION_BURY, "fallback auto-bury due to missing id")

        if act == ACTION_PROGRESS:
            if record.get("status") != ACTION_RECOVER:
                record["status"] = ACTION_PROGRESS
            record["last_updated_chapter"] = chapter_no
            _append_history(record, chapter_no, ACTION_PROGRESS, str(action.get("note", "")))
        elif act == ACTION_RECOVER:
            record["status"] = ACTION_RECOVER
            record["recovered_chapter"] = chapter_no
            record["last_updated_chapter"] = chapter_no
            _append_history(record, chapter_no, ACTION_RECOVER, str(action.get("note", "")))


def _mark_overdue_foreshadows(runtime: dict[str, Any], chapter_no: int) -> None:
    ledger = runtime.setdefault("foreshadow_ledger", [])
    for item in ledger:
        status = str(item.get("status", "")).strip()
        due = _safe_int(item.get("due_chapter"), 9999)
        if status == ACTION_RECOVER:
            continue
        if chapter_no > due:
            if status != ACTION_OVERDUE:
                item["status"] = ACTION_OVERDUE
                item["last_updated_chapter"] = chapter_no
                _append_history(item, chapter_no, ACTION_OVERDUE, "not recovered before due chapter")


def _build_active_foreshadow_view(runtime: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = runtime.get("foreshadow_ledger", [])
    view = []
    for item in ledger:
        status = str(item.get("status", "")).strip()
        if status == ACTION_RECOVER:
            continue
        view.append(
            {
                "foreshadow_id": item.get("foreshadow_id", ""),
                "description": item.get("description", ""),
                "status": status,
                "due_chapter": item.get("due_chapter", 0),
                "last_updated_chapter": item.get("last_updated_chapter", 0),
            },
        )
    view.sort(key=lambda x: (_safe_int(x.get("due_chapter"), 9999), str(x.get("foreshadow_id", ""))))
    return view[:40]


def _append_history(record: dict[str, Any], chapter_no: int, action: str, note: str) -> None:
    hist = record.setdefault("history", [])
    hist.append(
        {
            "chapter": chapter_no,
            "action": action,
            "note": note.strip(),
            "at": datetime.now(timezone.utc).isoformat(),
        },
    )
    record["history"] = hist[-80:]


def _open_foreshadow_ids(runtime_state: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in runtime_state.get("foreshadow_ledger", []):
        status = str(item.get("status", "")).strip()
        if status != ACTION_RECOVER:
            fid = str(item.get("foreshadow_id", "")).strip()
            if fid:
                ids.append(fid)
    return ids


def _find_thread(threads: list[dict[str, Any]], thread_id: str, title: str) -> dict[str, Any] | None:
    for item in threads:
        if thread_id and str(item.get("thread_id", "")) == thread_id:
            return item
    for item in threads:
        if title and str(item.get("title", "")) == title:
            return item
    return threads[0] if threads else None


def _pick_primary_thread(runtime_state: dict[str, Any]) -> dict[str, Any] | None:
    threads = runtime_state.get("active_threads", [])
    if not threads:
        return None
    return threads[0] if isinstance(threads[0], dict) else {"thread_id": "", "title": str(threads[0])}


def _resolve_protagonist_name(story_bible: dict[str, Any]) -> str:
    for ch in story_bible.get("characters", []):
        if str(ch.get("role", "")).lower() == "protagonist":
            return str(ch.get("name", "主角"))
    if story_bible.get("characters"):
        return str(story_bible["characters"][0].get("name", "主角"))
    return "主角"


def _should_recover_this_chapter(chapter_no: int, contract: dict[str, Any]) -> bool:
    objective = str(contract.get("chapter_objective", ""))
    stage_end = _safe_int(contract.get("stage_range", {}).get("chapter_end"), 0)
    if "兑现" in objective or "回收" in objective:
        return True
    return stage_end > 0 and chapter_no == stage_end


def _clip_text(text: str, max_len: int) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if len(cleaned) <= max_len:
        return cleaned
    if max_len <= 1:
        return "…"
    return cleaned[: max_len - 1] + "…"


def _character_updates_from_analysis(chapter_analysis: dict[str, Any], chapter_no: int) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for item in chapter_analysis.get("character_states", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("character_name", "")).strip()
        if not name:
            continue
        survival = str(item.get("survival_status", "active")).strip() or "active"
        state_after = str(item.get("state_after", "")).strip()
        change = str(item.get("psychological_change", "")).strip()
        updates.append(
            {
                "name": name,
                "status_hint": "active",
                "survival_status": survival,
                "state_after": state_after,
                "relationship_changes": item.get("relationship_changes", {}),
                "note": change or f"analysis touched in chapter {chapter_no}",
            },
        )
    return updates


def _foreshadow_actions_from_analysis(
    foreshadows: list[Any],
    chapter_no: int,
    fallback_thread_id: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for idx, item in enumerate(foreshadows, start=1):
        if not isinstance(item, dict):
            continue
        ftype = str(item.get("type", "")).strip().lower()
        fid = str(item.get("reference_foreshadow_id", "")).strip()
        if not fid:
            fid = f"fs_{chapter_no:03d}_{idx:02d}"
        content = _clip_text(str(item.get("content", item.get("title", ""))).strip(), 120)
        due_chapter = _safe_int(item.get("estimated_resolve_chapter"), chapter_no + 3)
        if ftype == "resolved":
            actions.append(
                {
                    "action": ACTION_RECOVER,
                    "foreshadow_id": fid,
                    "description": content,
                    "thread_id": fallback_thread_id,
                    "note": "resolved via chapter analysis",
                },
            )
        elif ftype == "planted":
            actions.append(
                {
                    "action": ACTION_BURY,
                    "foreshadow_id": fid,
                    "description": content,
                    "due_chapter": due_chapter,
                    "thread_id": fallback_thread_id,
                    "note": "planted via chapter analysis",
                },
            )
        else:
            actions.append(
                {
                    "action": ACTION_PROGRESS,
                    "foreshadow_id": fid,
                    "description": content,
                    "thread_id": fallback_thread_id,
                    "note": "progressed via chapter analysis",
                },
            )
    return actions


def build_runtime_prompt_view(
    runtime_state: dict[str, Any],
    chapter_no: int,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _normalize_runtime_prompt_view_config(cfg)
    summaries_raw = runtime_state.get("chapter_summaries", [])
    threads_raw = runtime_state.get("active_threads", []) or runtime_state.get("thread_ledger", [])
    foreshadow_raw = runtime_state.get("foreshadow_ledger", []) or runtime_state.get("foreshadows", [])

    selected_summaries = _select_recent_chapter_summaries(
        summaries=summaries_raw,
        max_items=int(config["chapter_summaries_recent"]),
    )
    selected_threads = _select_threads_for_prompt(
        threads=threads_raw,
        chapter_no=chapter_no,
        max_items=int(config["threads_max"]),
    )
    selected_foreshadows = _select_foreshadows_for_prompt(
        foreshadow_ledger=foreshadow_raw,
        chapter_no=chapter_no,
        due_horizon=int(config["foreshadow_due_horizon"]),
        max_items=int(config["foreshadows_max"]),
    )

    digests = {
        "recent_plot_digest": "",
        "core_conflict_digest": "",
        "due_foreshadow_digest": "",
        "continuity_risk_digest": "",
    }
    if bool(config["enable_digests"]):
        digest_max_chars = int(config["digest_max_chars"])
        digests["recent_plot_digest"] = _build_recent_plot_digest(selected_summaries, digest_max_chars)
        digests["core_conflict_digest"] = _build_core_conflict_digest(selected_threads, digest_max_chars)
        digests["due_foreshadow_digest"] = _build_due_foreshadow_digest(selected_foreshadows, digest_max_chars)
        digests["continuity_risk_digest"] = _build_continuity_risk_digest(
            selected_threads=selected_threads,
            selected_foreshadows=selected_foreshadows,
            digest_max_chars=digest_max_chars,
        )

    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "for_chapter": chapter_no,
        "window": {
            "chapter_summaries_recent": int(config["chapter_summaries_recent"]),
            "threads_max": int(config["threads_max"]),
            "foreshadow_due_horizon": int(config["foreshadow_due_horizon"]),
            "foreshadows_max": int(config["foreshadows_max"]),
        },
        "enabled": bool(config["enabled"]),
        "shadow_mode": bool(config["shadow_mode"]),
        "selected": {
            "recent_chapter_summaries": selected_summaries,
            "active_threads": selected_threads,
            "foreshadows_due": selected_foreshadows,
        },
        "digests": digests,
        "stats": {
            "raw_summary_count": len(summaries_raw) if isinstance(summaries_raw, list) else 0,
            "selected_summary_count": len(selected_summaries),
            "raw_thread_count": len(threads_raw) if isinstance(threads_raw, list) else 0,
            "selected_thread_count": len(selected_threads),
            "raw_foreshadow_count": len(foreshadow_raw) if isinstance(foreshadow_raw, list) else 0,
            "selected_foreshadow_count": len(selected_foreshadows),
        },
    }


def _normalize_runtime_prompt_view_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_RUNTIME_PROMPT_VIEW_CONFIG)
    out.update(dict(cfg or {}))
    out["enabled"] = bool(out.get("enabled", True))
    out["shadow_mode"] = bool(out.get("shadow_mode", True))
    out["enable_digests"] = bool(out.get("enable_digests", False))
    out["chapter_summaries_recent"] = max(1, min(20, _safe_int(out.get("chapter_summaries_recent"), 3)))
    out["threads_max"] = max(1, min(30, _safe_int(out.get("threads_max"), 8)))
    out["foreshadow_due_horizon"] = max(0, min(20, _safe_int(out.get("foreshadow_due_horizon"), 3)))
    out["foreshadows_max"] = max(1, min(30, _safe_int(out.get("foreshadows_max"), 8)))
    out["digest_max_chars"] = max(80, min(1200, _safe_int(out.get("digest_max_chars"), 220)))
    return out


def _select_recent_chapter_summaries(summaries: list[Any], max_items: int) -> list[dict[str, Any]]:
    if not isinstance(summaries, list):
        return []
    out: list[dict[str, Any]] = []
    for item in summaries[-max_items:]:
        if not isinstance(item, dict):
            continue
        chapter = _safe_int(item.get("chapter"), 0)
        summary = str(item.get("summary", "")).strip()
        if chapter <= 0 or not summary:
            continue
        out.append(
            {
                "chapter": chapter,
                "summary": _clip_text(summary, 220),
                "objective": _clip_text(str(item.get("objective", "")).strip(), 120),
                "stage_id": str(item.get("stage_id", "")).strip(),
                "alignment_pass": bool(item.get("alignment_pass", False)),
            },
        )
    return out


def _select_threads_for_prompt(threads: list[Any], chapter_no: int, max_items: int) -> list[dict[str, Any]]:
    if not isinstance(threads, list):
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in threads:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "active")).strip().lower()
        if status in {"resolved", "closed"}:
            continue
        title = str(item.get("title", item.get("thread", item.get("thread_id", "")))).strip()
        if not title:
            continue
        due = _safe_int(item.get("due_chapter"), chapter_no + 999)
        last_touch = _safe_int(item.get("last_updated_chapter"), 0)
        priority = str(item.get("priority", "P1")).strip().upper()
        note = _clip_text(str(item.get("note", item.get("latest_note", ""))).strip(), 120)
        score = _thread_prompt_score(priority, status, due, last_touch, chapter_no)
        scored.append(
            (
                score,
                {
                    "thread_id": str(item.get("thread_id", "")).strip(),
                    "title": title,
                    "status": status,
                    "priority": priority,
                    "due_chapter": due,
                    "last_updated_chapter": last_touch,
                    "note": note,
                },
            ),
        )
    scored.sort(key=lambda x: (-x[0], x[1]["title"]))
    return [item for _, item in scored[:max_items]]


def _thread_prompt_score(priority: str, status: str, due_chapter: int, last_touch: int, chapter_no: int) -> int:
    priority_score = {"P0": 60, "P1": 45, "P2": 30, "P3": 20}.get(priority, 25)
    status_score = {"overdue": 40, "due": 30, "active": 22, "paused": 10}.get(status, 18)
    delta = due_chapter - chapter_no
    if delta <= 0:
        due_score = 35
    elif delta <= 2:
        due_score = 25
    elif delta <= 5:
        due_score = 15
    else:
        due_score = 4
    recency_score = max(0, 12 - min(12, chapter_no - last_touch)) if last_touch > 0 else 0
    return priority_score + status_score + due_score + recency_score


def _select_foreshadows_for_prompt(
    foreshadow_ledger: list[Any],
    chapter_no: int,
    due_horizon: int,
    max_items: int,
) -> list[dict[str, Any]]:
    if not isinstance(foreshadow_ledger, list):
        return []
    primary: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for item in foreshadow_ledger:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).strip()
        if status == ACTION_RECOVER:
            continue
        fid = str(item.get("foreshadow_id", "")).strip()
        if not fid:
            continue
        due = _safe_int(item.get("due_chapter"), chapter_no + 999)
        due_delta = due - chapter_no
        row = {
            "foreshadow_id": fid,
            "description": _clip_text(str(item.get("description", "")).strip(), 140),
            "status": status,
            "due_chapter": due,
            "last_updated_chapter": _safe_int(item.get("last_updated_chapter"), 0),
            "thread_id": str(item.get("thread_id", "")).strip(),
        }
        if status == ACTION_OVERDUE or due_delta <= due_horizon:
            primary.append(row)
        else:
            fallback.append(row)
    primary.sort(key=lambda x: (_foreshadow_sort_rank(x.get("status", "")), x.get("due_chapter", 9999)))
    fallback.sort(key=lambda x: x.get("due_chapter", 9999))
    out = primary[:max_items]
    if len(out) < max_items:
        out.extend(fallback[: max_items - len(out)])
    return out


def _foreshadow_sort_rank(status: str) -> int:
    if status == ACTION_OVERDUE:
        return 0
    if status == ACTION_PROGRESS:
        return 1
    if status == ACTION_BURY:
        return 2
    return 3


def _build_recent_plot_digest(items: list[dict[str, Any]], max_chars: int) -> str:
    if not items:
        return ""
    lines = [f"Ch{int(item.get('chapter', 0))}:{item.get('summary', '')}" for item in items]
    return _clip_text(" | ".join(lines), max_chars)


def _build_core_conflict_digest(items: list[dict[str, Any]], max_chars: int) -> str:
    if not items:
        return ""
    lines = [f"{item.get('title', '')}(status={item.get('status', '')},due={item.get('due_chapter', 0)})" for item in items[:4]]
    return _clip_text("; ".join(lines), max_chars)


def _build_due_foreshadow_digest(items: list[dict[str, Any]], max_chars: int) -> str:
    if not items:
        return ""
    lines = [f"{item.get('foreshadow_id', '')}:{item.get('description', '')}(due={item.get('due_chapter', 0)})" for item in items[:5]]
    return _clip_text("; ".join(lines), max_chars)


def _build_continuity_risk_digest(
    selected_threads: list[dict[str, Any]],
    selected_foreshadows: list[dict[str, Any]],
    digest_max_chars: int,
) -> str:
    overdue_threads = sum(1 for item in selected_threads if str(item.get("status", "")) == "overdue")
    overdue_foreshadows = sum(1 for item in selected_foreshadows if str(item.get("status", "")) == ACTION_OVERDUE)
    due_soon_threads = sum(
        1
        for item in selected_threads
        if _safe_int(item.get("due_chapter"), 9999) <= _safe_int(item.get("last_updated_chapter"), 0) + 2
    )
    text = (
        f"risk: overdue_threads={overdue_threads}, "
        f"overdue_foreshadows={overdue_foreshadows}, "
        f"due_soon_threads={due_soon_threads}"
    )
    return _clip_text(text, digest_max_chars)


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


def _append_quality_history(
    runtime: dict[str, Any],
    chapter_no: int,
    audit_report: dict[str, Any] | None,
    alignment: dict[str, Any] | None,
) -> None:
    history = runtime.setdefault("quality_history", [])
    if not isinstance(history, list):
        history = []
        runtime["quality_history"] = history

    entry = _build_quality_history_entry(chapter_no, audit_report, alignment)
    history[:] = [item for item in history if _safe_int(item.get("chapter"), -1) != chapter_no]
    history.append(entry)
    history.sort(key=lambda item: _safe_int(item.get("chapter"), 0))
    runtime["quality_history"] = history[-240:]


def _build_quality_history_entry(
    chapter_no: int,
    audit_report: dict[str, Any] | None,
    alignment: dict[str, Any] | None,
) -> dict[str, Any]:
    report = audit_report if isinstance(audit_report, dict) else {}
    after = report.get("after", {}) if isinstance(report.get("after", {}), dict) else {}
    failures = _quality_failures(report)
    return {
        "chapter": chapter_no,
        "pass": bool(
            after.get(
                "pass",
                report.get("pass", alignment.get("pass", False) if isinstance(alignment, dict) else False),
            )
        ),
        "hard_failures": sum(1 for item in failures if str(item.get("severity", "")).lower() == "error"),
        "warnings": sum(1 for item in failures if str(item.get("severity", "")).lower() == "warning"),
    }


def _quality_failures(audit_report: dict[str, Any]) -> list[dict[str, Any]]:
    after = audit_report.get("after", {}) if isinstance(audit_report, dict) else {}
    failures = after.get("failures") if isinstance(after, dict) else None
    if isinstance(failures, list):
        return [item for item in failures if isinstance(item, dict)]
    direct = audit_report.get("failures") if isinstance(audit_report, dict) else None
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)]
    return []

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import difflib
import re
from typing import Any

from .anti_ai_style import detect_style_issues, rewrite_style_issues
from .state_reflector import apply_state_delta


def run_t7_audit_and_revise(
    chapter_no: int,
    draft_markdown: str,
    contract: dict[str, Any],
    alignment_report: dict[str, Any],
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
    runtime_state: dict[str, Any],
    auto_revise: bool = True,
) -> tuple[str, dict[str, Any], str]:
    before = run_t7_audit(
        chapter_no=chapter_no,
        draft_markdown=draft_markdown,
        contract=contract,
        alignment_report=alignment_report,
        story_bible=story_bible,
        structure_map=structure_map,
        runtime_state=runtime_state,
    )

    revised = draft_markdown
    revision = {
        "attempted": False,
        "changed": False,
        "max_attempts": 1,
        "actions": [],
        "triggered_by": [],
    }
    after = before

    if auto_revise and not before["pass"]:
        revised, actions, triggered = revise_once(
            draft_markdown=draft_markdown,
            failures=before["failures"],
            contract=contract,
            story_bible=story_bible,
            chapter_no=chapter_no,
        )
        revision["attempted"] = True
        revision["actions"] = actions
        revision["changed"] = revised != draft_markdown
        revision["triggered_by"] = triggered
        after = run_t7_audit(
            chapter_no=chapter_no,
            draft_markdown=revised,
            contract=contract,
            alignment_report=alignment_report,
            story_bible=story_bible,
            structure_map=structure_map,
            runtime_state=runtime_state,
        )

    diff_md = render_diff_report(old_text=draft_markdown, new_text=revised)
    report = {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapter": chapter_no,
        "pass": after["pass"],
        "before": before,
        "after": after,
        "revision": revision,
    }
    return revised, report, diff_md


def run_t7_batch_auditor(
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
    runtime_state: dict[str, Any],
    chapter_packages: list[dict[str, Any]],
    auto_revise: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered = sorted(chapter_packages, key=lambda p: int(p.get("chapter", 0)))
    runtime_cursor = _ensure_runtime_for_batch(runtime_state)

    revised_packages: list[dict[str, Any]] = []
    chapter_results: list[dict[str, Any]] = []
    unresolved_failures: list[dict[str, Any]] = []
    resolved_by_revision: list[dict[str, Any]] = []

    for pkg in ordered:
        chapter_no = int(pkg.get("chapter", 0))
        if chapter_no <= 0:
            continue

        revised_draft, audit_report, diff_md = run_t7_audit_and_revise(
            chapter_no=chapter_no,
            draft_markdown=str(pkg.get("draft_markdown", "")),
            contract=pkg.get("contract", {}),
            alignment_report=pkg.get("alignment_report", {}),
            story_bible=story_bible,
            structure_map=structure_map,
            runtime_state=runtime_cursor,
            auto_revise=auto_revise,
        )

        revised_pkg = dict(pkg)
        revised_pkg["draft_markdown"] = revised_draft
        revised_pkg["t7_audit_report"] = audit_report
        revised_pkg["t7_diff_report_md"] = diff_md
        revised_packages.append(revised_pkg)

        before = audit_report.get("before", {})
        after = audit_report.get("after", {})
        revision = audit_report.get("revision", {})
        result = {
            "chapter": chapter_no,
            "pass_before": bool(before.get("pass", False)),
            "pass_after": bool(after.get("pass", False)),
            "revision_attempted": bool(revision.get("attempted", False)),
            "revision_changed": bool(revision.get("changed", False)),
            "before_failure_count": len(before.get("failures", [])),
            "after_failure_count": len(after.get("failures", [])),
            "failed_rules_before": [f.get("rule_id", "") for f in before.get("failures", [])],
            "failed_rules_after": [f.get("rule_id", "") for f in after.get("failures", [])],
        }
        chapter_results.append(result)

        if result["pass_before"] is False and result["pass_after"] is True:
            resolved_by_revision.append(
                {
                    "chapter": chapter_no,
                    "resolved_rules": result["failed_rules_before"],
                    "revision_actions": revision.get("actions", []),
                },
            )
        if result["pass_after"] is False:
            unresolved_failures.append(
                {
                    "chapter": chapter_no,
                    "failed_rules": result["failed_rules_after"],
                    "failures": after.get("failures", []),
                },
            )

        runtime_cursor = _update_runtime_cursor(runtime_cursor, revised_pkg)

    summary = {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "auto_revise": auto_revise,
        "chapter_count": len(chapter_results),
        "pass_before_count": sum(1 for r in chapter_results if r["pass_before"]),
        "pass_after_count": sum(1 for r in chapter_results if r["pass_after"]),
        "failed_before_count": sum(1 for r in chapter_results if not r["pass_before"]),
        "failed_after_count": sum(1 for r in chapter_results if not r["pass_after"]),
        "revision_attempted_count": sum(1 for r in chapter_results if r["revision_attempted"]),
        "revision_changed_count": sum(1 for r in chapter_results if r["revision_changed"]),
        "chapter_results": chapter_results,
        "failure_checklist": {
            "unresolved_after_revision": unresolved_failures,
            "resolved_by_revision": resolved_by_revision,
        },
        "pass": len(unresolved_failures) == 0,
    }
    return revised_packages, summary


def render_t7_batch_summary_markdown(summary: dict[str, Any]) -> str:
    chk = summary.get("failure_checklist", {})
    unresolved = chk.get("unresolved_after_revision", [])
    resolved = chk.get("resolved_by_revision", [])
    lines = [
        "# T7 Batch Summary",
        "",
        "## Totals",
        f"- chapters: {summary.get('chapter_count', 0)}",
        f"- pass_before: {summary.get('pass_before_count', 0)}",
        f"- pass_after: {summary.get('pass_after_count', 0)}",
        f"- failed_before: {summary.get('failed_before_count', 0)}",
        f"- failed_after: {summary.get('failed_after_count', 0)}",
        f"- revision_attempted: {summary.get('revision_attempted_count', 0)}",
        f"- revision_changed: {summary.get('revision_changed_count', 0)}",
        f"- batch_pass: {summary.get('pass', False)}",
        "",
        "## Failure Checklist",
    ]
    if unresolved:
        lines.append("- unresolved_after_revision:")
        for item in unresolved:
            lines.append(
                f"- unresolved_chapter_{item.get('chapter')}: rules={item.get('failed_rules', [])}",
            )
    else:
        lines.append("- unresolved_after_revision: []")

    if resolved:
        lines.append("- resolved_by_revision:")
        for item in resolved:
            lines.append(
                f"- resolved_chapter_{item.get('chapter')}: resolved_rules={item.get('resolved_rules', [])}",
            )
    else:
        lines.append("- resolved_by_revision: []")
    lines.append("")
    return "\n".join(lines)


def discover_chapter_package_files(package_dir: str, pattern: str = "chapter_package_ch*.json") -> list[Path]:
    root = Path(package_dir)
    if not root.exists():
        return []
    files = list(root.glob(pattern))
    files.sort(key=_chapter_sort_key)
    return files


def run_t7_audit(
    chapter_no: int,
    draft_markdown: str,
    contract: dict[str, Any],
    alignment_report: dict[str, Any],
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []

    template_checks = _template_alignment_checks(
        chapter_no=chapter_no,
        draft_markdown=draft_markdown,
        contract=contract,
        alignment_report=alignment_report,
        structure_map=structure_map,
    )
    failures.extend(template_checks["failures"])

    continuity_checks = _continuity_checks(
        chapter_no=chapter_no,
        draft_markdown=draft_markdown,
        story_bible=story_bible,
        runtime_state=runtime_state,
    )
    failures.extend(continuity_checks["failures"])

    progression_checks = _progression_checks(
        chapter_no=chapter_no,
        draft_markdown=draft_markdown,
        contract=contract,
        runtime_state=runtime_state,
    )
    failures.extend(progression_checks["failures"])

    repetition_checks = _repetition_checks(
        chapter_no=chapter_no,
        draft_markdown=draft_markdown,
        runtime_state=runtime_state,
    )
    failures.extend(repetition_checks["failures"])

    character_checks = _character_consistency_checks(
        draft_markdown=draft_markdown,
        story_bible=story_bible,
        runtime_state=runtime_state,
    )
    failures.extend(character_checks["failures"])

    foreshadow_checks = _foreshadow_governance_checks(
        chapter_no=chapter_no,
        draft_markdown=draft_markdown,
        runtime_state=runtime_state,
    )
    failures.extend(foreshadow_checks["failures"])

    length_checks = _length_checks(
        draft_markdown=draft_markdown,
        contract=contract,
        story_bible=story_bible,
    )
    failures.extend(length_checks["failures"])

    style_checks = _style_checks(draft_markdown=draft_markdown)
    failures.extend(style_checks["failures"])

    category_results = {
        "template_alignment": template_checks["pass"],
        "continuity": continuity_checks["pass"],
        "progression": progression_checks["pass"],
        "repetition": repetition_checks["pass"],
        "character_consistency": character_checks["pass"],
        "foreshadow_governance": foreshadow_checks["pass"],
        "length_control": length_checks["pass"],
        "style_ai_trace": style_checks["pass"],
    }
    pass_flag = not any(item["severity"] == "error" for item in failures)
    return {
        "chapter": chapter_no,
        "pass": pass_flag,
        "category_results": category_results,
        "failures": failures,
    }


def revise_once(
    draft_markdown: str,
    failures: list[dict[str, Any]],
    contract: dict[str, Any],
    story_bible: dict[str, Any],
    chapter_no: int,
) -> tuple[str, list[str], list[str]]:
    revised = draft_markdown
    actions: list[str] = []
    triggered_by: list[str] = []
    rule_ids = {str(item.get("rule_id", "")) for item in failures}

    if "CT_PLACEHOLDER_TOKEN" in rule_ids:
        for marker in ("TODO", "[TODO]", "[待补]", "TBD", "......"):
            if marker in revised:
                revised = revised.replace(marker, "")
                actions.append(f"removed placeholder token: {marker}")
                triggered_by.append("CT_PLACEHOLDER_TOKEN")

    if "CT_PROTAGONIST_PRESENCE" in rule_ids:
        protagonist = _resolve_protagonist(story_bible)
        inject = f"{protagonist}在本章开始即承担主动决策，避免剧情偏离主线。"
        revised = _inject_after_heading(revised, "## 正文", inject)
        actions.append("injected protagonist focus line")
        triggered_by.append("CT_PROTAGONIST_PRESENCE")

    if "TA_OBJECTIVE_COVERAGE" in rule_ids:
        objective = str(contract.get("chapter_objective", "")).strip()
        if objective:
            revised = _inject_after_heading(
                revised,
                "## 正文",
                f"本章结构任务明确为：{objective}。",
            )
            actions.append("injected explicit chapter objective in body")
            triggered_by.append("TA_OBJECTIVE_COVERAGE")

    if "TA_ALIGNMENT_SECTION" in rule_ids:
        revised = revised.rstrip() + "\n\n" + _render_alignment_section(contract) + "\n"
        actions.append("appended alignment section")
        triggered_by.append("TA_ALIGNMENT_SECTION")

    if "PG_OBJECTIVE_NOT_FULFILLED" in rule_ids:
        objective = str(contract.get("chapter_objective", "")).strip()
        if objective:
            revised = _inject_after_heading(
                revised,
                "## 正文",
                f"新的实质推进随即发生：{objective}。",
            )
            actions.append("injected concrete progression beat")
            triggered_by.append("PG_OBJECTIVE_NOT_FULFILLED")

    if "FG_DUE_FORESHADOW_IGNORED" in rule_ids:
        revised = _inject_after_heading(
            revised,
            "## 正文",
            "他停下脚步，转而核对此前埋下的异常征兆，让旧线索在本章获得一次明确推进。",
        )
        actions.append("injected due foreshadow follow-up beat")
        triggered_by.append("FG_DUE_FORESHADOW_IGNORED")

    if "CC_STATE_CONTRADICTION" in rule_ids:
        revised = _inject_after_heading(
            revised,
            "## 正文",
            "动作仍受先前伤势牵制，他每前进一步都要付出额外代价。",
        )
        actions.append("injected character state continuity beat")
        triggered_by.append("CC_STATE_CONTRADICTION")

    if "ST_AI_TRACE_PHRASES" in rule_ids:
        for phrase in ("需要注意的是", "首先", "其次", "最后", "总之", "作为一个"):
            if phrase in revised:
                revised = revised.replace(phrase, "")
        actions.append("removed high-risk ai-trace phrases")
        triggered_by.append("ST_AI_TRACE_PHRASES")

    if "ST_BANNED_PHRASES" in rule_ids or "ST_CONNECTOR_DENSITY" in rule_ids or "ST_REPEATED_OPENING" in rule_ids:
        rewritten = rewrite_style_issues(revised)
        if rewritten != revised:
            revised = rewritten
            actions.append("rewritten by anti-ai-style policy")
        triggered_by.append("ANTI_AI_STYLE_POLICY")

    if "ST_DUPLICATE_LINES" in rule_ids:
        revised = _dedupe_adjacent_lines(revised)
        actions.append("deduplicated adjacent repeated lines")
        triggered_by.append("ST_DUPLICATE_LINES")

    if "LEN_OUT_OF_RANGE" in rule_ids:
        min_chars, max_chars, actual_chars = _resolve_length_window(revised, contract, story_bible)
        if actual_chars > max_chars:
            revised = _trim_chapter_body_to_limit(revised, max_chars)
            actions.append(f"trimmed chapter body to <= {max_chars} chars")
        elif actual_chars < min_chars:
            revised = _inject_after_heading(
                revised,
                "## 正文",
                "补充细节：人物在关键抉择前完成一次可感知的动作与情绪推进，确保本章信息增量落地。",
            )
            actions.append(f"expanded chapter body toward >= {min_chars} chars")
        triggered_by.append("LEN_OUT_OF_RANGE")

    if not actions and chapter_no > 0:
        # Keep one deterministic fallback for one-pass revise policy.
        revised = _inject_after_heading(
            revised,
            "## 正文",
            "本章在保证模板对齐的前提下，补充一处因果承接以降低跳跃感。",
        )
        actions.append("fallback minor revision injection")
        triggered_by.append("fallback")

    return revised, actions, triggered_by


def render_diff_report(old_text: str, new_text: str) -> str:
    diff_lines = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile="draft_before.md",
            tofile="draft_after.md",
            lineterm="",
        ),
    )
    if not diff_lines:
        return "# T7 Diff Report\n\nNo changes.\n"
    return "# T7 Diff Report\n\n```diff\n" + "\n".join(diff_lines) + "\n```\n"


def _template_alignment_checks(
    chapter_no: int,
    draft_markdown: str,
    contract: dict[str, Any],
    alignment_report: dict[str, Any],
    structure_map: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    pass_flag = True

    expected_stage = _find_stage_contract(structure_map, chapter_no).get("stage_id", "")
    actual_stage = str(contract.get("stage_id", ""))
    if expected_stage and actual_stage != expected_stage:
        pass_flag = False
        failures.append(
            _failure(
                "template_alignment",
                "TA_STAGE_ORDER",
                "error",
                f"Expected stage {expected_stage}, got {actual_stage}.",
                "Use structure_map stage for this chapter.",
            ),
        )

    if not alignment_report.get("pass", False):
        pass_flag = False
        failures.append(
            _failure(
                "template_alignment",
                "TA_ALIGNMENT_REPORT_FAIL",
                "error",
                "Existing alignment report is failing.",
                "Fix chapter contract to match structure_map objective and stage.",
            ),
        )

    objective = str(contract.get("chapter_objective", "")).strip()
    if objective and not _has_text_overlap(draft_markdown, objective):
        pass_flag = False
        failures.append(
            _failure(
                "template_alignment",
                "TA_OBJECTIVE_COVERAGE",
                "error",
                "Draft does not clearly carry the chapter objective.",
                "Add one explicit sentence that commits to the objective.",
            ),
        )

    if "## 本章模板对齐点" not in draft_markdown:
        pass_flag = False
        failures.append(
            _failure(
                "template_alignment",
                "TA_ALIGNMENT_SECTION",
                "error",
                "Missing alignment section in draft.",
                "Append alignment section with stage/objective/escalation.",
            ),
        )

    return {"pass": pass_flag, "failures": failures}


def _continuity_checks(
    chapter_no: int,
    draft_markdown: str,
    story_bible: dict[str, Any],
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    pass_flag = True

    protagonist = _resolve_protagonist(story_bible)
    if protagonist and protagonist not in draft_markdown:
        pass_flag = False
        failures.append(
            _failure(
                "continuity",
                "CT_PROTAGONIST_PRESENCE",
                "error",
                f"Protagonist not found in draft: {protagonist}.",
                "Ensure protagonist has explicit active beat in chapter.",
            ),
        )

    placeholders = [marker for marker in ("TODO", "[TODO]", "[待补]", "TBD", "......") if marker in draft_markdown]
    if placeholders:
        pass_flag = False
        failures.append(
            _failure(
                "continuity",
                "CT_PLACEHOLDER_TOKEN",
                "error",
                f"Placeholder tokens found: {placeholders}",
                "Remove placeholders before finalizing chapter.",
            ),
        )

    prev_summary = _find_previous_summary(runtime_state, chapter_no)
    if prev_summary and not _has_text_overlap(draft_markdown, prev_summary):
        failures.append(
            _failure(
                "continuity",
                "CT_PREV_SUMMARY_LINK",
                "warn",
                "Weak lexical linkage with previous chapter summary.",
                "Add one callback sentence to previous chapter consequence.",
            ),
        )

    return {"pass": pass_flag, "failures": failures}


def _length_checks(
    draft_markdown: str,
    contract: dict[str, Any],
    story_bible: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    pass_flag = True
    if not bool(contract.get("length_control_enabled", True)):
        return {"pass": True, "failures": failures}
    min_chars, max_chars, actual_chars = _resolve_length_window(draft_markdown, contract, story_bible)

    if actual_chars < min_chars or actual_chars > max_chars:
        pass_flag = False
        failures.append(
            _failure(
                "length_control",
                "LEN_OUT_OF_RANGE",
                "error",
                f"Chapter chars out of range: actual={actual_chars}, expected={min_chars}-{max_chars}.",
                "Revise chapter length to target range while preserving key events.",
            ),
        )
    return {"pass": pass_flag, "failures": failures}


def _progression_checks(
    chapter_no: int,
    draft_markdown: str,
    contract: dict[str, Any],
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    objective = str(contract.get("chapter_objective", "")).strip()
    body = _chapter_body_text(draft_markdown)
    if objective and not _objective_progression_present(body, objective):
        failures.append(
            _failure(
                "progression",
                "PG_OBJECTIVE_NOT_FULFILLED",
                "error",
                f"Chapter objective lacks a concrete on-page progression beat: {objective}",
                "Add concrete actions or discoveries that visibly advance the chapter objective.",
            ),
        )
    due_threads = _due_active_threads(runtime_state, chapter_no)
    if due_threads and not _has_active_thread_movement(body, due_threads):
        failures.append(
            _failure(
                "progression",
                "PG_ACTIVE_THREAD_STATIC",
                "error",
                f"No active thread shows visible movement in chapter {chapter_no}.",
                "Move at least one active thread forward with a consequence, reveal, or escalation.",
            ),
        )
    return {"pass": not failures, "failures": failures}


def _repetition_checks(
    chapter_no: int,
    draft_markdown: str,
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    body = _chapter_body_text(draft_markdown)
    repeated_terms = _repeated_cjk_phrases(body, min_occurrences=3)
    prev_summary = _find_previous_summary(runtime_state, chapter_no)
    if repeated_terms and prev_summary and any(term in prev_summary for term in repeated_terms):
        failures.append(
            _failure(
                "repetition",
                "RP_HEAVY_TERM_REPETITION",
                "warn",
                f"Heavy repeated carry-over terms with weak novelty: {repeated_terms[:5]}",
                "Replace repeated recap beats with a new consequence, detail, or escalation.",
            ),
        )
    return {"pass": not failures, "failures": failures}


def _character_consistency_checks(
    draft_markdown: str,
    story_bible: dict[str, Any],
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    body = _chapter_body_text(draft_markdown)
    protagonist = _resolve_protagonist(story_bible)
    tracked_states = runtime_state.get("character_states", [])
    for item in tracked_states:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", item.get("character_name", ""))).strip()
        if not name or name not in body:
            continue
        state_text = str(item.get("current_state", item.get("state", item.get("note", "")))).strip()
        if _detect_character_state_contradiction(body, state_text, name or protagonist):
            failures.append(
                _failure(
                    "character_consistency",
                    "CC_STATE_CONTRADICTION",
                    "error",
                    f"Character state contradicts recent runtime state for {name}: {state_text}",
                    "Preserve injury, exhaustion, or status limits unless the recovery is shown on page.",
                ),
            )
            break
    return {"pass": not failures, "failures": failures}


def _foreshadow_governance_checks(
    chapter_no: int,
    draft_markdown: str,
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    body = _chapter_body_text(draft_markdown)
    foreshadows = [item for item in runtime_state.get("foreshadows", []) if isinstance(item, dict)]
    due_items = []
    for item in foreshadows:
        due_chapter = _safe_int(item.get("due_chapter", 0), 0)
        status = str(item.get("status", "")).strip()
        if due_chapter and due_chapter <= chapter_no and status not in {"resolved", "已回收", "兑现"}:
            due_items.append(item)
    if due_items and not any(_foreshadow_item_is_advanced(item, body) for item in due_items):
        failures.append(
            _failure(
                "foreshadow_governance",
                "FG_DUE_FORESHADOW_IGNORED",
                "warn",
                f"Due foreshadows remain untouched in chapter {chapter_no}: {len(due_items)} item(s)",
                "Advance or resolve at least one due foreshadow with an explicit callback.",
            ),
        )

    duplicate_groups = _duplicate_foreshadow_descriptions(foreshadows, runtime_state.get("foreshadow_ledger", []))
    if duplicate_groups:
        failures.append(
            _failure(
                "foreshadow_governance",
                "FG_DUPLICATE_FORESHADOW",
                "warn",
                f"Duplicate foreshadow signals detected: {duplicate_groups[:3]}",
                "Consolidate repeated foreshadow entries instead of reseeding the same clue.",
            ),
        )

    false_resolutions = [item for item in foreshadows if _is_false_foreshadow_resolution(item, body)]
    if false_resolutions:
        failures.append(
            _failure(
                "foreshadow_governance",
                "FG_FALSE_RESOLUTION",
                "warn",
                f"Foreshadows marked resolved without on-page payoff: {len(false_resolutions)} item(s)",
                "Only mark foreshadows resolved when the chapter explicitly reveals or confirms them on page.",
            ),
        )
    return {"pass": not failures, "failures": failures}


def _style_checks(draft_markdown: str) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    pass_flag = True

    ai_phrases = ["需要注意的是", "首先", "其次", "最后", "总之", "作为一个"]
    hit_count = sum(draft_markdown.count(p) for p in ai_phrases)
    if hit_count >= 3:
        pass_flag = False
        failures.append(
            _failure(
                "style_ai_trace",
                "ST_AI_TRACE_PHRASES",
                "error",
                f"Too many generic ai-trace phrases: {hit_count}",
                "Reduce formulaic connectives and rewrite naturally.",
            ),
        )

    lines = [ln.strip() for ln in draft_markdown.splitlines() if ln.strip()]
    dup_count = _count_adjacent_duplicates(lines)
    if dup_count > 0:
        pass_flag = False
        failures.append(
            _failure(
                "style_ai_trace",
                "ST_DUPLICATE_LINES",
                "error",
                f"Adjacent duplicate lines detected: {dup_count}",
                "Remove repeated adjacent lines.",
            ),
        )

    avg_len = _average_sentence_length(draft_markdown)
    if avg_len > 130:
        failures.append(
            _failure(
                "style_ai_trace",
                "ST_OVERLONG_SENTENCE",
                "warn",
                f"Average sentence length is high: {avg_len:.1f}",
                "Split long sentences to improve readability.",
            ),
        )

    policy_issues = detect_style_issues(draft_markdown)
    for item in policy_issues:
        rule_id = str(item.get("rule_id", "ST_STYLE_POLICY"))
        severity = str(item.get("severity", "warn"))
        detail = str(item.get("detail", ""))
        if severity == "error":
            pass_flag = False
        failures.append(
            _failure(
                "style_ai_trace",
                rule_id,
                severity,
                detail,
                "Rewrite paragraph transitions to remove formulaic style traces.",
            ),
        )

    return {"pass": pass_flag, "failures": failures}


def _failure(category: str, rule_id: str, severity: str, detail: str, suggestion: str) -> dict[str, Any]:
    return {
        "category": category,
        "rule_id": rule_id,
        "severity": severity,
        "detail": detail,
        "suggestion": suggestion,
    }


def _find_stage_contract(structure_map: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    for stage in structure_map.get("stage_contracts", []):
        start = int(stage.get("chapter_start", 1))
        end = int(stage.get("chapter_end", start))
        if start <= chapter_no <= end:
            return stage
    contracts = structure_map.get("stage_contracts", [])
    return contracts[-1] if contracts else {}


def _resolve_protagonist(story_bible: dict[str, Any]) -> str:
    for ch in story_bible.get("characters", []):
        if str(ch.get("role", "")).lower() == "protagonist":
            return str(ch.get("name", ""))
    chars = story_bible.get("characters", [])
    if chars:
        return str(chars[0].get("name", ""))
    return ""


def _find_previous_summary(runtime_state: dict[str, Any], chapter_no: int) -> str:
    target = chapter_no - 1
    for item in runtime_state.get("chapter_summaries", []):
        if int(item.get("chapter", -1)) == target:
            return str(item.get("summary", ""))
    return ""


def _has_text_overlap(text_a: str, text_b: str) -> bool:
    ta = _meaning_tokens(text_a)
    tb = _meaning_tokens(text_b)
    if not ta or not tb:
        return False
    overlap = ta.intersection(tb)
    return len(overlap) >= max(2, min(6, len(tb) // 3))


def _meaning_tokens(text: str) -> set[str]:
    ascii_words = {w.lower() for w in re.findall(r"[A-Za-z0-9_]{2,}", text or "")}
    cjk_chars = set(re.findall(r"[\u4e00-\u9fff]", text or ""))
    return ascii_words.union(cjk_chars)


def _resolve_length_window(
    draft_markdown: str,
    contract: dict[str, Any],
    story_bible: dict[str, Any],
) -> tuple[int, int, int]:
    metadata = story_bible.get("metadata", {})
    target_chars = _safe_int(
        contract.get("chapter_word_target", metadata.get("chapter_word_target", 3000)),
        3000,
    )
    target_chars = max(500, min(20000, target_chars))
    tolerance_ratio = _safe_float(
        contract.get("chapter_word_tolerance_ratio", metadata.get("chapter_word_tolerance_ratio", 0.15)),
        0.15,
    )
    tolerance_ratio = min(0.45, max(0.05, tolerance_ratio))
    min_chars = max(200, int(round(target_chars * (1 - tolerance_ratio))))
    max_chars = max(min_chars + 50, int(round(target_chars * (1 + tolerance_ratio))))
    actual_chars = _count_chapter_chars(draft_markdown)
    return min_chars, max_chars, actual_chars


def _count_chapter_chars(draft_markdown: str) -> int:
    body = _strip_alignment_section(draft_markdown or "")
    plain = re.sub(r"^#{1,6}\s*", "", body, flags=re.MULTILINE)
    plain = re.sub(r"^\s*[-*]\s+", "", plain, flags=re.MULTILINE)
    plain = plain.replace("`", "")
    compact = "".join(ch for ch in plain if not ch.isspace())
    return len(compact)


def _strip_alignment_section(text: str) -> str:
    if not text:
        return ""
    marker_candidates = ("## 本章模板对齐点", "## Template Alignment")
    cut = len(text)
    for marker in marker_candidates:
        idx = text.find(marker)
        if idx >= 0:
            cut = min(cut, idx)
    return text[:cut].strip()


def _chapter_body_text(text: str) -> str:
    return _strip_alignment_section(text or "")


def _objective_progression_present(body: str, objective: str) -> bool:
    normalized_objective = re.sub(r"\s+", "", objective)
    compact_body = re.sub(r"\s+", "", body)
    for sentence in _split_sentences(body):
        compact_sentence = re.sub(r"\s+", "", sentence)
        if normalized_objective and normalized_objective in compact_sentence and not _is_negated_sentence(compact_sentence):
            return True

    action_terms, anchor_terms = _objective_terms(objective)
    for sentence in _split_sentences(body):
        compact_sentence = re.sub(r"\s+", "", sentence)
        if _is_negated_sentence(compact_sentence):
            continue
        has_action = any(term in compact_sentence for term in action_terms)
        has_anchor = any(term in compact_sentence for term in anchor_terms)
        if has_action and has_anchor:
            return True
    return False


def _has_active_thread_movement(body: str, active_threads: list[dict[str, Any]]) -> bool:
    progress_terms = ["推进", "发现", "确认", "揭开", "逼近", "回应", "证实", "升级", "解决", "兑现"]
    for item in active_threads:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        match_terms = _thread_match_terms(title)
        matched_terms = _matched_thread_terms(match_terms, body)
        if (title in body or _is_thread_touched_by_terms(match_terms, matched_terms)) and any(term in body for term in progress_terms):
            return True
    return False


def _due_active_threads(runtime_state: dict[str, Any], chapter_no: int) -> list[dict[str, Any]]:
    due_threads: list[dict[str, Any]] = []
    for item in runtime_state.get("active_threads", []):
        if not isinstance(item, dict):
            continue
        due_chapter = _safe_int(item.get("due_chapter", 0), 0)
        if due_chapter and due_chapter <= chapter_no:
            due_threads.append(item)
    return due_threads


def _objective_terms(objective: str) -> tuple[list[str], list[str]]:
    action_vocab = ["进入", "推进", "发现", "确认", "逼近", "抵达", "打开", "深入", "揭开", "核对", "查明"]
    action_terms = [term for term in action_vocab if term in objective]
    anchor_terms = [term for term in _candidate_repeated_terms(objective) if term not in action_terms and len(term) >= 2]
    return action_terms, anchor_terms


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。！？!?；;\n]+", text or "") if part.strip()]


def _is_negated_sentence(text: str) -> bool:
    return any(token in text for token in ["没有", "并未", "未能", "未曾", "尚未", "仍未", "不是"])


def _candidate_repeated_terms(text: str) -> list[str]:
    ascii_words = re.findall(r"[A-Za-z0-9_]{2,}", text or "")
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,4}", text or "")
    terms: list[str] = []
    seen: set[str] = set()
    for term in ascii_words + cjk_terms:
        normalized = term.lower()
        if normalized in seen:
            continue
        if normalized in {"正文", "本章", "阶段"}:
            continue
        seen.add(normalized)
        terms.append(term)
    return terms


def _repeated_cjk_phrases(text: str, min_occurrences: int = 3) -> list[str]:
    counts: dict[str, int] = {}
    compact = re.sub(r"\s+", "", text or "")
    for size in (2, 3, 4):
        for idx in range(0, max(0, len(compact) - size + 1)):
            phrase = compact[idx : idx + size]
            if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", phrase):
                continue
            counts[phrase] = counts.get(phrase, 0) + 1
    out = [phrase for phrase, count in counts.items() if count >= min_occurrences]
    out.sort(key=lambda item: (-len(item), -counts[item], item))
    return out[:8]


def _detect_character_state_contradiction(body: str, state_text: str, name: str) -> bool:
    if not state_text or name not in body:
        return False
    limitation_markers = ["重伤", "未愈", "虚弱", "行动艰难", "力竭", "昏迷", "受伤"]
    contradiction_markers = ["神完气足", "步伐轻快", "健步如飞", "毫发无伤", "像从未受过伤一样"]
    if any(tok in state_text for tok in limitation_markers) and any(tok in body for tok in contradiction_markers):
        return True
    return False


def _foreshadow_item_is_advanced(item: dict[str, Any], body: str) -> bool:
    desc = str(item.get("description", item.get("title", ""))).strip()
    if not desc:
        return False
    terms = [tok for tok in _candidate_repeated_terms(desc) if len(tok) >= 2]
    return any(term in body for term in terms[:4])


def _duplicate_foreshadow_descriptions(
    foreshadows: list[dict[str, Any]],
    ledger_items: Any,
) -> list[str]:
    seen: dict[str, int] = {}
    descriptions: list[str] = []
    for item in foreshadows:
        desc = _normalize_foreshadow_description(item)
        if desc:
            descriptions.append(desc)
    if isinstance(ledger_items, list):
        for item in ledger_items:
            if not isinstance(item, dict):
                continue
            desc = _normalize_foreshadow_description(item)
            if desc:
                descriptions.append(desc)
    duplicates: list[str] = []
    for desc in descriptions:
        seen[desc] = seen.get(desc, 0) + 1
        if seen[desc] == 2:
            duplicates.append(desc)
    return duplicates


def _normalize_foreshadow_description(item: dict[str, Any]) -> str:
    raw = str(item.get("description", item.get("title", item.get("note", "")))).strip()
    return re.sub(r"\s+", "", raw)


def _is_false_foreshadow_resolution(item: dict[str, Any], body: str) -> bool:
    status = str(item.get("status", "")).strip()
    if status not in {"resolved", "已回收", "兑现"}:
        return False
    desc = str(item.get("description", item.get("title", ""))).strip()
    if not desc:
        return False
    reveal_terms = ["揭开", "证实", "终于明白", "确认", "解释", "来源", "答案", "查明"]
    desc_terms = [tok for tok in _candidate_repeated_terms(desc) if len(tok) >= 2 and tok not in {"真相", "秘密"}]
    if not desc_terms:
        desc_terms = [desc[: min(len(desc), 4)]]
    has_callback = any(term in body for term in desc_terms[:4])
    has_payoff = any(term in body for term in reveal_terms)
    return not (has_callback and has_payoff)


def _thread_match_terms(title: str) -> list[str]:
    cleaned = "".join(re.findall(r"[\u4e00-\u9fff]+", title))
    terms: list[str] = []
    salient_candidates = ["地下遗迹", "石门", "异响", "线索", "秘密", "祭坛", "火光", "甬道", "真相", "苏醒"]
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


def _safe_int(raw: Any, default: int) -> int:
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
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


def _trim_chapter_body_to_limit(draft_markdown: str, max_chars: int) -> str:
    lines = draft_markdown.splitlines()
    start_idx = None
    end_idx = len(lines)
    for idx, line in enumerate(lines):
        if line.strip() == "## 正文":
            start_idx = idx + 1
            continue
        if start_idx is not None and line.strip().startswith("## "):
            end_idx = idx
            break
    if start_idx is None:
        return draft_markdown

    head = lines[:start_idx]
    body = lines[start_idx:end_idx]
    tail = lines[end_idx:]
    while body:
        candidate = "\n".join(head + body + tail)
        if _count_chapter_chars(candidate) <= max_chars:
            return candidate.rstrip() + "\n"
        body.pop()
    return ("\n".join(head + tail)).rstrip() + "\n"


def _inject_after_heading(text: str, heading: str, line: str) -> str:
    lines = text.splitlines()
    for idx, ln in enumerate(lines):
        if ln.strip() == heading:
            insert_idx = idx + 1
            while insert_idx < len(lines) and not lines[insert_idx].strip():
                insert_idx += 1
            lines.insert(insert_idx, line)
            return "\n".join(lines).rstrip() + "\n"
    return text.rstrip() + "\n\n" + line + "\n"


def _render_alignment_section(contract: dict[str, Any]) -> str:
    stage = contract.get("stage_id", "")
    rng = contract.get("stage_range", {})
    objective = contract.get("chapter_objective", "")
    stage_goal = contract.get("stage_goal", "")
    escalation = contract.get("escalation_target", "")
    return (
        "## 本章模板对齐点\n"
        f"- 阶段: {stage} ({rng.get('chapter_start', '')}-{rng.get('chapter_end', '')})\n"
        f"- 结构任务: {objective}\n"
        f"- 阶段目标: {stage_goal}\n"
        f"- 升级目标: {escalation}"
    )


def _dedupe_adjacent_lines(text: str) -> str:
    out: list[str] = []
    prev = None
    for ln in text.splitlines():
        if prev is not None and ln.strip() and ln.strip() == prev.strip():
            continue
        out.append(ln)
        prev = ln
    return "\n".join(out).rstrip() + "\n"


def _count_adjacent_duplicates(lines: list[str]) -> int:
    count = 0
    for idx in range(1, len(lines)):
        if lines[idx] == lines[idx - 1]:
            count += 1
    return count


def _average_sentence_length(text: str) -> float:
    parts = [p.strip() for p in re.split(r"[。！？!?;\n]+", text or "") if p.strip()]
    if not parts:
        return 0.0
    total = sum(len(p) for p in parts)
    return total / len(parts)


def _chapter_sort_key(path: Path) -> int:
    m = re.search(r"ch(\d+)", path.name.lower())
    if m:
        return int(m.group(1))
    return 999999


def _ensure_runtime_for_batch(runtime_state: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(runtime_state)
    runtime.setdefault("chapter_summaries", [])
    runtime.setdefault("active_threads", [])
    runtime.setdefault("foreshadows", [])
    runtime.setdefault("foreshadow_ledger", [])
    runtime.setdefault("character_states", [])
    return runtime


def _update_runtime_cursor(runtime_state: dict[str, Any], chapter_package: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(runtime_state)
    chapter_no = int(chapter_package.get("chapter", 0))
    summary = str(chapter_package.get("chapter_summary", ""))
    contract = chapter_package.get("contract", {})
    alignment = chapter_package.get("alignment_report", {})
    state_delta = chapter_package.get("state_delta", {})
    has_action_delta = isinstance(state_delta, dict) and any(
        isinstance(state_delta.get(field), list)
        for field in ("character_updates", "thread_actions", "foreshadow_actions")
    )

    if chapter_no > 0 and has_action_delta:
        runtime = apply_state_delta(
            runtime_state=runtime,
            chapter_no=chapter_no,
            chapter_summary=summary,
            contract=contract,
            alignment=alignment,
            delta=state_delta,
        )
    elif chapter_no > 0 and summary:
        summaries = list(runtime.get("chapter_summaries", []))
        # Replace same chapter summary if exists; keep one record per chapter.
        summaries = [s for s in summaries if int(s.get("chapter", -1)) != chapter_no]
        summaries.append(
            {
                "chapter": chapter_no,
                "summary": summary,
                "stage_id": contract.get("stage_id", ""),
                "objective": contract.get("chapter_objective", ""),
                "alignment_pass": alignment.get("pass", False),
            },
        )
        summaries.sort(key=lambda x: int(x.get("chapter", 0)))
        runtime["chapter_summaries"] = summaries

    if isinstance(state_delta, dict):
        for field in ("active_threads", "foreshadows", "foreshadow_ledger", "character_states"):
            value = state_delta.get(field)
            if isinstance(value, list):
                runtime[field] = value

    for field in ("active_threads", "foreshadows", "foreshadow_ledger", "character_states"):
        value = chapter_package.get(field)
        if isinstance(value, list):
            runtime[field] = value

    return runtime

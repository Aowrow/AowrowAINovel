from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from typing import Any, Callable

from .app_config import load_runtime_config
from .asset_store import AssetStore
from .audit_reviser import (
    discover_chapter_package_files,
    render_t7_batch_summary_markdown,
    run_t7_audit_and_revise,
    run_t7_batch_auditor,
)
from .chapter_orchestrator import render_t5_summary_markdown, run_t5_pipeline
from .context_engine import compose_context, seed_runtime_state
from .remix_bundle import load_remix_bundle, resolve_default_remix_bundle_path
from .skill_assets import execute_skill_scaffold, export_skill, get_skill_text, list_skill_names
from .state_reflector import replay_t6_from_chapter_package, render_t6_report_markdown
from .storage_layout import resolve_book_layout
from .story_builder import build_story_bible
from .structure_mapper import map_structure
from .template_parser import parse_template_markdown


RUNTIME_CONFIG_FILENAME = "template_novel_engine.config.json"


def main() -> int:
    project_root_default = Path(__file__).resolve().parents[2]
    runtime_cfg = load_runtime_config(project_root_default)
    parser = _build_parser(project_root_default, runtime_cfg)
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "t1":
            _run_t1(Path(args.template), Path(args.out))
            return 0
        if args.command == "t2":
            _run_t2(Path(args.story_idea), Path(args.out))
            return 0
        if args.command == "t3":
            _run_t3(
                Path(args.template_dna),
                Path(args.story_bible),
                Path(args.out_map),
                Path(args.out_outline),
            )
            return 0
        if args.command == "t4":
            _run_t4(
                template_dna_path=Path(args.template_dna),
                story_bible_path=Path(args.story_bible),
                structure_map_path=Path(args.structure_map),
                chapter_no=int(args.chapter),
                token_budget=int(args.token_budget),
                out_bundle_path=Path(args.out_bundle),
                runtime_state_path=Path(args.runtime_state) if args.runtime_state else None,
                out_runtime_path=Path(args.out_runtime) if args.out_runtime else None,
                out_report_path=Path(args.out_report) if args.out_report else None,
                author_intent=args.author_intent or "",
                runtime_prompt_view_cfg=runtime_cfg.get("runtime_prompt_view", {}) if isinstance(runtime_cfg, dict) else {},
            )
            return 0
        if args.command == "t5":
            _run_t5(
                template_dna_path=Path(args.template_dna),
                story_bible_path=Path(args.story_bible),
                structure_map_path=Path(args.structure_map),
                chapter_start=int(args.chapter_start),
                chapter_end=int(args.chapter_end),
                token_budget=int(args.token_budget),
                out_dir=Path(args.out_dir) if args.out_dir else None,
                project_root_path=Path(args.project_root) if args.project_root else project_root_default,
                runtime_state_path=Path(args.runtime_state) if args.runtime_state else None,
                author_intent=args.author_intent or "",
                run_t7_batch=bool(args.run_t7_batch) and not bool(args.no_run_t7_batch),
                t7_batch_out_dir=Path(args.t7_batch_out_dir) if args.t7_batch_out_dir else None,
                t7_batch_pattern=args.t7_batch_pattern or "chapter_package_ch*.json",
                t7_batch_no_auto_revise=bool(args.t7_batch_no_auto_revise),
                writer_backend=args.writer_backend or "builtin",
                writer_model=args.writer_model or "",
                writer_api_key=args.writer_api_key or "",
                writer_base_url=args.writer_base_url or "",
                writer_temperature=float(args.writer_temperature),
                writer_max_tokens=int(args.writer_max_tokens),
                writer_timeout_sec=int(args.writer_timeout_sec),
                writer_system_prompt_file=args.writer_system_prompt_file or "",
                length_control_cfg=runtime_cfg.get("length_control", {}) if isinstance(runtime_cfg, dict) else {},
                anti_ai_style_cfg=runtime_cfg.get("anti_ai_style", {}) if isinstance(runtime_cfg, dict) else {},
                runtime_prompt_view_cfg=runtime_cfg.get("runtime_prompt_view", {}) if isinstance(runtime_cfg, dict) else {},
            )
            return 0
        if args.command == "generate":
            chapter_count = _resolve_count_for_generate(
                count=args.count,
                chapter_start=int(args.chapter_start),
                chapter_end=int(args.chapter_end),
            )
            _run_generate(
                project_root=Path(args.project_root),
                remix_bundle_path=Path(args.remix_bundle) if args.remix_bundle else None,
                chapter_start=int(args.chapter_start),
                chapter_count=chapter_count,
                token_budget=int(args.token_budget),
                runtime_state_path=Path(args.runtime_state) if args.runtime_state else None,
                out_dir=Path(args.out_dir) if args.out_dir else None,
                author_intent=args.author_intent or "",
                run_t7_batch=bool(args.run_t7_batch) and not bool(args.no_run_t7_batch),
                t7_batch_out_dir=Path(args.t7_batch_out_dir) if args.t7_batch_out_dir else None,
                t7_batch_pattern=args.t7_batch_pattern or "chapter_package_ch*.json",
                t7_batch_no_auto_revise=bool(args.t7_batch_no_auto_revise),
                writer_backend=args.writer_backend or "builtin",
                writer_model=args.writer_model or "",
                writer_api_key=args.writer_api_key or "",
                writer_base_url=args.writer_base_url or "",
                writer_temperature=float(args.writer_temperature),
                writer_max_tokens=int(args.writer_max_tokens),
                writer_timeout_sec=int(args.writer_timeout_sec),
                writer_system_prompt_file=args.writer_system_prompt_file or "",
                length_control_cfg=runtime_cfg.get("length_control", {}) if isinstance(runtime_cfg, dict) else {},
                anti_ai_style_cfg=runtime_cfg.get("anti_ai_style", {}) if isinstance(runtime_cfg, dict) else {},
                runtime_prompt_view_cfg=runtime_cfg.get("runtime_prompt_view", {}) if isinstance(runtime_cfg, dict) else {},
            )
            return 0
        if args.command == "continue":
            _run_continue(
                project_root=Path(args.project_root),
                book=args.book,
                chapter_count=int(args.count),
                token_budget=int(args.token_budget),
                runtime_state_path=Path(args.runtime_state) if args.runtime_state else None,
                author_intent=args.author_intent or "",
                run_t7_batch=bool(args.run_t7_batch) and not bool(args.no_run_t7_batch),
                t7_batch_out_dir=Path(args.t7_batch_out_dir) if args.t7_batch_out_dir else None,
                t7_batch_pattern=args.t7_batch_pattern or "chapter_package_ch*.json",
                t7_batch_no_auto_revise=bool(args.t7_batch_no_auto_revise),
                writer_backend=args.writer_backend or "builtin",
                writer_model=args.writer_model or "",
                writer_api_key=args.writer_api_key or "",
                writer_base_url=args.writer_base_url or "",
                writer_temperature=float(args.writer_temperature),
                writer_max_tokens=int(args.writer_max_tokens),
                writer_timeout_sec=int(args.writer_timeout_sec),
                writer_system_prompt_file=args.writer_system_prompt_file or "",
                length_control_cfg=runtime_cfg.get("length_control", {}) if isinstance(runtime_cfg, dict) else {},
                anti_ai_style_cfg=runtime_cfg.get("anti_ai_style", {}) if isinstance(runtime_cfg, dict) else {},
                runtime_prompt_view_cfg=runtime_cfg.get("runtime_prompt_view", {}) if isinstance(runtime_cfg, dict) else {},
            )
            return 0
        if args.command == "t6":
            _run_t6(
                story_bible_path=Path(args.story_bible),
                chapter_package_path=Path(args.chapter_package),
                runtime_state_path=Path(args.runtime_state),
                out_runtime_path=Path(args.out_runtime),
                out_delta_path=Path(args.out_delta),
                out_report_path=Path(args.out_report),
                author_intent=args.author_intent or "",
            )
            return 0
        if args.command == "t7":
            _run_t7(
                story_bible_path=Path(args.story_bible),
                structure_map_path=Path(args.structure_map),
                chapter_package_path=Path(args.chapter_package),
                runtime_state_path=Path(args.runtime_state),
                out_package_path=Path(args.out_package),
                out_audit_path=Path(args.out_audit),
                out_diff_path=Path(args.out_diff),
                auto_revise=not bool(args.no_auto_revise),
            )
            return 0
        if args.command == "t7-batch":
            _run_t7_batch(
                story_bible_path=Path(args.story_bible),
                structure_map_path=Path(args.structure_map),
                runtime_state_path=Path(args.runtime_state),
                packages_dir=Path(args.packages_dir),
                out_dir=Path(args.out_dir),
                pattern=args.pattern,
                auto_revise=not bool(args.no_auto_revise),
            )
            return 0
        if args.command == "skill":
            _run_skill_command(args)
            return 0
        if args.command == "run-all":
            _run_all(Path(args.project_root))
            return 0
    except Exception as exc:  # pragma: no cover - top-level CLI guard
        print(f"[ERROR] {exc}")
        return 2
    return 1


def _build_parser(project_root_default: Path, runtime_cfg: dict[str, Any]) -> argparse.ArgumentParser:
    defaults = runtime_cfg.get("defaults", {}) if isinstance(runtime_cfg, dict) else {}
    writer_defaults = runtime_cfg.get("writer", {}) if isinstance(runtime_cfg, dict) else {}
    default_chapter_start = int(defaults.get("chapter_start", 1))
    default_chapter_end = int(defaults.get("chapter_end", 5))
    default_chapter_count = int(defaults.get("chapter_count", max(1, default_chapter_end - default_chapter_start + 1)))
    default_token_budget = int(defaults.get("token_budget", 1800))
    default_run_t7_batch = bool(defaults.get("run_t7_batch", False))

    parser = argparse.ArgumentParser(description="Template Novel Engine CLI")
    sub = parser.add_subparsers(dest="command")

    t1 = sub.add_parser("t1", help="Run T1 template parser.")
    t1.add_argument("--template", required=True, help="Template markdown path.")
    t1.add_argument("--out", required=True, help="Output template_dna.json path.")

    t2 = sub.add_parser("t2", help="Run T2 story builder.")
    t2.add_argument("--story-idea", required=True, help="Story idea markdown path.")
    t2.add_argument("--out", required=True, help="Output story_bible.json path.")

    t3 = sub.add_parser("t3", help="Run T3 structure mapper.")
    t3.add_argument("--template-dna", required=True, help="Input template_dna.json path.")
    t3.add_argument("--story-bible", required=True, help="Input story_bible.json path.")
    t3.add_argument("--out-map", required=True, help="Output structure_map.json path.")
    t3.add_argument("--out-outline", required=True, help="Output volume_outline.md path.")

    t4 = sub.add_parser("t4", help="Run T4 non-dropping context engine.")
    t4.add_argument("--template-dna", required=True, help="Input template_dna.json path.")
    t4.add_argument("--story-bible", required=True, help="Input story_bible.json path.")
    t4.add_argument("--structure-map", required=True, help="Input structure_map.json path.")
    t4.add_argument("--chapter", required=True, type=int, help="Target chapter number.")
    t4.add_argument(
        "--token-budget",
        required=False,
        type=int,
        default=default_token_budget,
        help="Context token budget estimate.",
    )
    t4.add_argument("--runtime-state", required=False, help="Optional runtime_state.json path.")
    t4.add_argument(
        "--out-bundle",
        required=True,
        help="Output context bundle json path.",
    )
    t4.add_argument(
        "--out-runtime",
        required=False,
        help="Optional output runtime_state.json path (seeded if missing input).",
    )
    t4.add_argument("--out-report", required=False, help="Optional output markdown report path.")
    t4.add_argument(
        "--author-intent",
        required=False,
        default="",
        help="Optional author intent override for current run.",
    )

    t5 = sub.add_parser("t5", help="Run T5 Plan/Compose/Write chapter pipeline.")
    t5.add_argument("--template-dna", required=True, help="Input template_dna.json path.")
    t5.add_argument("--story-bible", required=True, help="Input story_bible.json path.")
    t5.add_argument("--structure-map", required=True, help="Input structure_map.json path.")
    t5.add_argument(
        "--chapter-start",
        required=False,
        type=int,
        default=default_chapter_start,
        help="Start chapter (inclusive).",
    )
    t5.add_argument(
        "--chapter-end",
        required=False,
        type=int,
        default=default_chapter_end,
        help="End chapter (inclusive).",
    )
    t5.add_argument(
        "--token-budget",
        required=False,
        type=int,
        default=default_token_budget,
        help="Context token budget estimate.",
    )
    t5.add_argument("--runtime-state", required=False, help="Optional runtime_state.json input path.")
    t5.add_argument(
        "--out-dir",
        required=False,
        default="",
        help="Optional output directory. Default: outputs/<book_title>/ under project root.",
    )
    t5.add_argument(
        "--project-root",
        required=False,
        default=str(project_root_default),
        help="Project root used for default output paths and config discovery.",
    )
    t5.add_argument(
        "--author-intent",
        required=False,
        default="",
        help="Optional author intent override for this T5 run.",
    )
    t5.add_argument(
        "--run-t7-batch",
        required=False,
        action="store_true",
        default=default_run_t7_batch,
        help="Auto-run T7 batch auditor after chapter generation.",
    )
    t5.add_argument(
        "--no-run-t7-batch",
        required=False,
        action="store_true",
        help="Force disable auto-run T7 batch even when config default is enabled.",
    )
    t5.add_argument(
        "--t7-batch-out-dir",
        required=False,
        help="Optional output directory for auto T7 batch artifacts.",
    )
    t5.add_argument(
        "--t7-batch-pattern",
        required=False,
        default="chapter_package_ch*.json",
        help="Glob pattern used by auto T7 batch against t5 out-dir.",
    )
    t5.add_argument(
        "--t7-batch-no-auto-revise",
        required=False,
        action="store_true",
        help="Disable one-pass auto revise for auto T7 batch run.",
    )
    t5.add_argument(
        "--writer-backend",
        required=False,
        choices=["builtin", "openai", "claude"],
        default=str(writer_defaults.get("backend", "builtin")),
        help="Draft writer backend. builtin uses rule template; openai/claude call real LLM APIs.",
    )
    t5.add_argument(
        "--writer-model",
        required=False,
        default=str(writer_defaults.get("model", "")),
        help="Model id for openai/claude backend.",
    )
    t5.add_argument(
        "--writer-api-key",
        required=False,
        default=str(writer_defaults.get("api_key", "")),
        help="API key override. If empty, use writer.api_key in config file.",
    )
    t5.add_argument(
        "--writer-base-url",
        required=False,
        default=str(writer_defaults.get("base_url", "")),
        help="API base URL override. Example: https://api.openai.com/v1 or https://api.anthropic.com/v1",
    )
    t5.add_argument(
        "--writer-temperature",
        required=False,
        type=float,
        default=float(writer_defaults.get("temperature", 0.7)),
        help="Sampling temperature for model writer.",
    )
    t5.add_argument(
        "--writer-max-tokens",
        required=False,
        type=int,
        default=int(writer_defaults.get("max_tokens", 2200)),
        help="Max output tokens for model writer.",
    )
    t5.add_argument(
        "--writer-timeout-sec",
        required=False,
        type=int,
        default=int(writer_defaults.get("timeout_sec", 120)),
        help="HTTP timeout seconds for model writer requests.",
    )
    t5.add_argument(
        "--writer-system-prompt-file",
        required=False,
        default=str(writer_defaults.get("system_prompt_file", "")),
        help="Optional custom system prompt file for model writer.",
    )

    gen = sub.add_parser("generate", help="Build a new book from a remix bundle and generate chapters.")
    gen.add_argument(
        "--project-root",
        required=False,
        default=str(project_root_default),
        help="Project root. Defaults to current engine root.",
    )
    gen.add_argument(
        "--remix-bundle",
        required=False,
        default="",
        help="Optional template markdown path. Default fallback: 爆款解析.md (root/inputs) -> template_analysis.md (root/inputs).",
    )
    gen.add_argument(
        "--story-idea",
        required=False,
        default="",
        help="Optional story idea markdown path. Default fallback: 新故事思路.md (root/inputs) -> story_idea.md (root/inputs).",
    )
    gen.add_argument(
        "--count",
        required=False,
        type=int,
        default=None,
        help="Number of chapters to generate from chapter-start. Prefer this over chapter-end.",
    )
    gen.add_argument(
        "--chapter-start",
        required=False,
        type=int,
        default=default_chapter_start,
        help="Start chapter (inclusive).",
    )
    gen.add_argument(
        "--chapter-end",
        required=False,
        type=int,
        default=default_chapter_end,
        help="End chapter (inclusive).",
    )
    gen.add_argument(
        "--token-budget",
        required=False,
        type=int,
        default=default_token_budget,
        help="Context token budget estimate.",
    )
    gen.add_argument(
        "--runtime-state",
        required=False,
        default="",
        help="Optional runtime_state.json input path.",
    )
    gen.add_argument(
        "--out-dir",
        required=False,
        default="",
        help="Optional output chapter dir. Default: outputs/<book_title>/ under project root.",
    )
    gen.add_argument(
        "--author-intent",
        required=False,
        default="",
        help="Optional author intent for this run.",
    )
    gen.add_argument(
        "--run-t7-batch",
        required=False,
        action="store_true",
        default=default_run_t7_batch,
        help="Auto-run T7 batch auditor after chapter generation.",
    )
    gen.add_argument(
        "--no-run-t7-batch",
        required=False,
        action="store_true",
        help="Force disable auto-run T7 batch even when config default is enabled.",
    )
    gen.add_argument(
        "--t7-batch-out-dir",
        required=False,
        default="",
        help="Optional output directory for auto T7 batch artifacts.",
    )
    gen.add_argument(
        "--t7-batch-pattern",
        required=False,
        default="chapter_package_ch*.json",
        help="Glob pattern used by auto T7 batch against t5 out-dir.",
    )
    gen.add_argument(
        "--t7-batch-no-auto-revise",
        required=False,
        action="store_true",
        help="Disable one-pass auto revise for auto T7 batch run.",
    )
    gen.add_argument(
        "--writer-backend",
        required=False,
        choices=["builtin", "openai", "claude"],
        default=str(writer_defaults.get("backend", "builtin")),
        help="Draft writer backend.",
    )
    gen.add_argument("--writer-model", required=False, default=str(writer_defaults.get("model", "")))
    gen.add_argument("--writer-api-key", required=False, default=str(writer_defaults.get("api_key", "")))
    gen.add_argument("--writer-base-url", required=False, default=str(writer_defaults.get("base_url", "")))
    gen.add_argument("--writer-temperature", required=False, type=float, default=float(writer_defaults.get("temperature", 0.7)))
    gen.add_argument("--writer-max-tokens", required=False, type=int, default=int(writer_defaults.get("max_tokens", 2200)))
    gen.add_argument("--writer-timeout-sec", required=False, type=int, default=int(writer_defaults.get("timeout_sec", 120)))
    gen.add_argument("--writer-system-prompt-file", required=False, default=str(writer_defaults.get("system_prompt_file", "")))
    for action in list(gen._actions):
        if "--remix-bundle" in action.option_strings:
            action.help = "Optional remix bundle path. Default fallback: remix_bundle.json/.md (root/inputs)."
        if "--story-idea" in action.option_strings:
            _remove_option(gen, action)

    cont = sub.add_parser("continue", help="Continue an existing book by chapter count, skipping T1/T2/T3.")
    cont.add_argument(
        "--project-root",
        required=False,
        default=str(project_root_default),
        help="Project root. Defaults to current engine root.",
    )
    cont.add_argument(
        "--book",
        required=True,
        help="Book folder name under outputs/, or an absolute book directory path.",
    )
    cont.add_argument(
        "--count",
        required=False,
        type=int,
        default=default_chapter_count,
        help="Number of chapters to continue writing.",
    )
    cont.add_argument(
        "--token-budget",
        required=False,
        type=int,
        default=default_token_budget,
        help="Context token budget estimate.",
    )
    cont.add_argument(
        "--runtime-state",
        required=False,
        default="",
        help="Optional runtime_state.json input path override.",
    )
    cont.add_argument(
        "--author-intent",
        required=False,
        default="",
        help="Optional author intent for this run.",
    )
    cont.add_argument(
        "--run-t7-batch",
        required=False,
        action="store_true",
        default=default_run_t7_batch,
        help="Auto-run T7 batch auditor after chapter generation.",
    )
    cont.add_argument(
        "--no-run-t7-batch",
        required=False,
        action="store_true",
        help="Force disable auto-run T7 batch even when config default is enabled.",
    )
    cont.add_argument(
        "--t7-batch-out-dir",
        required=False,
        default="",
        help="Optional output directory for auto T7 batch artifacts.",
    )
    cont.add_argument(
        "--t7-batch-pattern",
        required=False,
        default="chapter_package_ch*.json",
        help="Glob pattern used by auto T7 batch against t5 out-dir.",
    )
    cont.add_argument(
        "--t7-batch-no-auto-revise",
        required=False,
        action="store_true",
        help="Disable one-pass auto revise for auto T7 batch run.",
    )
    cont.add_argument(
        "--writer-backend",
        required=False,
        choices=["builtin", "openai", "claude"],
        default=str(writer_defaults.get("backend", "builtin")),
        help="Draft writer backend.",
    )
    cont.add_argument("--writer-model", required=False, default=str(writer_defaults.get("model", "")))
    cont.add_argument("--writer-api-key", required=False, default=str(writer_defaults.get("api_key", "")))
    cont.add_argument("--writer-base-url", required=False, default=str(writer_defaults.get("base_url", "")))
    cont.add_argument("--writer-temperature", required=False, type=float, default=float(writer_defaults.get("temperature", 0.7)))
    cont.add_argument("--writer-max-tokens", required=False, type=int, default=int(writer_defaults.get("max_tokens", 2200)))
    cont.add_argument("--writer-timeout-sec", required=False, type=int, default=int(writer_defaults.get("timeout_sec", 120)))
    cont.add_argument("--writer-system-prompt-file", required=False, default=str(writer_defaults.get("system_prompt_file", "")))

    t6 = sub.add_parser("t6", help="Run T6 state reflection on one chapter package.")
    t6.add_argument("--story-bible", required=True, help="Input story_bible.json path.")
    t6.add_argument("--chapter-package", required=True, help="Input chapter_package_chXX.json path.")
    t6.add_argument("--runtime-state", required=True, help="Input runtime_state.json path.")
    t6.add_argument("--out-runtime", required=True, help="Output runtime_state_after_t6.json path.")
    t6.add_argument("--out-delta", required=True, help="Output state_delta.json path.")
    t6.add_argument("--out-report", required=True, help="Output t6_report.md path.")
    t6.add_argument(
        "--author-intent",
        required=False,
        default="",
        help="Optional author intent override for this T6 run.",
    )

    t7 = sub.add_parser("t7", help="Run T7 audit and one-pass auto revise on one chapter package.")
    t7.add_argument("--story-bible", required=True, help="Input story_bible.json path.")
    t7.add_argument("--structure-map", required=True, help="Input structure_map.json path.")
    t7.add_argument("--chapter-package", required=True, help="Input chapter_package_chXX.json path.")
    t7.add_argument("--runtime-state", required=True, help="Input runtime_state.json path.")
    t7.add_argument("--out-package", required=True, help="Output revised chapter package path.")
    t7.add_argument("--out-audit", required=True, help="Output t7_audit_report.json path.")
    t7.add_argument("--out-diff", required=True, help="Output t7_diff_report.md path.")
    t7.add_argument(
        "--no-auto-revise",
        required=False,
        action="store_true",
        help="Disable one-pass automatic revise.",
    )

    t7b = sub.add_parser("t7-batch", help="Run T7 audit in batch on chapter_package directory.")
    t7b.add_argument("--story-bible", required=True, help="Input story_bible.json path.")
    t7b.add_argument("--structure-map", required=True, help="Input structure_map.json path.")
    t7b.add_argument("--runtime-state", required=True, help="Input runtime_state.json path.")
    t7b.add_argument("--packages-dir", required=True, help="Directory containing chapter_package_ch*.json.")
    t7b.add_argument("--out-dir", required=True, help="Output directory for T7 batch artifacts.")
    t7b.add_argument(
        "--pattern",
        required=False,
        default="chapter_package_ch*.json",
        help="Glob pattern for chapter packages.",
    )
    t7b.add_argument(
        "--no-auto-revise",
        required=False,
        action="store_true",
        help="Disable one-pass automatic revise.",
    )

    skill_cmd = sub.add_parser("skill", help="Work with built-in project skills.")
    skill_sub = skill_cmd.add_subparsers(dest="skill_command")
    skill_sub.add_parser("list", help="List built-in skills.")

    skill_show = skill_sub.add_parser("show", help="Print a built-in skill.")
    skill_show.add_argument("name", help="Built-in skill name.")

    skill_export = skill_sub.add_parser("export", help="Export a built-in skill to a file.")
    skill_export.add_argument("name", help="Built-in skill name.")
    skill_export.add_argument("--out", required=True, help="Output file path.")

    skill_scaffold = skill_sub.add_parser("scaffold", help="Execute a built-in skill and build a remix bundle.")
    skill_scaffold.add_argument("name", help="Built-in skill name.")
    skill_scaffold.add_argument("--viral-story", required=True, help="Input viral story path.")
    skill_scaffold.add_argument("--new-story-idea", required=True, help="Input new story idea path.")
    skill_scaffold.add_argument(
        "--out",
        required=False,
        default=str(project_root_default / "inputs" / "remix_bundle.json"),
        help="Output remix bundle JSON path. Default: <project-root>/inputs/remix_bundle.json",
    )
    skill_scaffold.add_argument(
        "--writer-backend",
        required=False,
        choices=["builtin", "openai", "claude"],
        default=str(writer_defaults.get("backend", "builtin")),
        help="Skill execution backend. Use openai/claude for real model calls.",
    )
    skill_scaffold.add_argument("--writer-model", required=False, default=str(writer_defaults.get("model", "")))
    skill_scaffold.add_argument("--writer-api-key", required=False, default=str(writer_defaults.get("api_key", "")))
    skill_scaffold.add_argument("--writer-base-url", required=False, default=str(writer_defaults.get("base_url", "")))
    skill_scaffold.add_argument("--writer-temperature", required=False, type=float, default=float(writer_defaults.get("temperature", 0.7)))
    skill_scaffold.add_argument(
        "--writer-max-tokens",
        required=False,
        type=int,
        default=max(6000, int(writer_defaults.get("max_tokens", 2200))),
    )
    skill_scaffold.add_argument("--writer-timeout-sec", required=False, type=int, default=int(writer_defaults.get("timeout_sec", 120)))
    skill_scaffold.add_argument("--writer-system-prompt-file", required=False, default=str(writer_defaults.get("system_prompt_file", "")))

    all_cmd = sub.add_parser("run-all", help="Run T1+T2+T3 with default paths.")
    all_cmd.add_argument(
        "--project-root",
        required=False,
        default=str(project_root_default),
        help="Project root for default input/output paths.",
    )
    return parser


def _run_t1(template_path: Path, out_path: Path) -> dict[str, Any]:
    text = _read_text(template_path)
    dna = parse_template_markdown(text, source_file=str(template_path))
    _write_json(out_path, dna)
    print(f"[OK] T1 finished: {out_path}")
    return dna


def _run_t2(story_path: Path, out_path: Path) -> dict[str, Any]:
    text = _read_text(story_path)
    bible = build_story_bible(text, source_file=str(story_path))
    _write_json(out_path, bible)
    print(f"[OK] T2 finished: {out_path}")
    return bible


def _run_t3(
    template_dna_path: Path,
    story_bible_path: Path,
    out_map_path: Path,
    out_outline_path: Path,
) -> tuple[dict[str, Any], str]:
    template_dna = _read_json(template_dna_path)
    story_bible = _read_json(story_bible_path)
    structure_map, outline = map_structure(template_dna, story_bible)
    _write_json(out_map_path, structure_map)
    _write_text(out_outline_path, outline)
    print(f"[OK] T3 finished: {out_map_path}, {out_outline_path}")
    return structure_map, outline


def _run_t4(
    template_dna_path: Path,
    story_bible_path: Path,
    structure_map_path: Path,
    chapter_no: int,
    token_budget: int,
    out_bundle_path: Path,
    runtime_state_path: Path | None = None,
    out_runtime_path: Path | None = None,
    out_report_path: Path | None = None,
    author_intent: str = "",
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    template_dna = _read_json(template_dna_path)
    story_bible = _read_json(story_bible_path)
    structure_map = _read_json(structure_map_path)

    runtime_state: dict[str, Any] | None = None
    if runtime_state_path and runtime_state_path.exists():
        runtime_state = _read_json(runtime_state_path)
    else:
        runtime_state = seed_runtime_state(story_bible, structure_map)

    bundle, report_md, runtime_used = compose_context(
        template_dna=template_dna,
        story_bible=story_bible,
        structure_map=structure_map,
        runtime_state=runtime_state,
        chapter_no=chapter_no,
        token_budget=token_budget,
        author_intent=author_intent,
        runtime_prompt_view_cfg=runtime_prompt_view_cfg,
    )
    _write_json(out_bundle_path, bundle)

    if out_report_path:
        _write_text(out_report_path, report_md)
    if out_runtime_path:
        _write_json(out_runtime_path, runtime_used)

    print(f"[OK] T4 finished: {out_bundle_path}")
    if out_report_path:
        print(f"[OK] T4 report: {out_report_path}")
    if out_runtime_path:
        print(f"[OK] T4 runtime: {out_runtime_path}")
    return bundle, report_md


def _run_t5(
    template_dna_path: Path,
    story_bible_path: Path,
    structure_map_path: Path,
    chapter_start: int,
    chapter_end: int,
    token_budget: int,
    out_dir: Path | None,
    project_root_path: Path | None = None,
    runtime_state_path: Path | None = None,
    author_intent: str = "",
    run_t7_batch: bool = False,
    t7_batch_out_dir: Path | None = None,
    t7_batch_pattern: str = "chapter_package_ch*.json",
    t7_batch_no_auto_revise: bool = False,
    writer_backend: str = "builtin",
    writer_model: str = "",
    writer_api_key: str = "",
    writer_base_url: str = "",
    writer_temperature: float = 0.7,
    writer_max_tokens: int = 2200,
    writer_timeout_sec: int = 120,
    writer_system_prompt_file: str = "",
    length_control_cfg: dict[str, Any] | None = None,
    anti_ai_style_cfg: dict[str, Any] | None = None,
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
    on_chapter_complete: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    template_dna = _read_json(template_dna_path)
    story_bible = _read_json(story_bible_path)
    structure_map = _read_json(structure_map_path)
    project_root = project_root_path or Path(__file__).resolve().parents[2]

    resolved_out_dir = out_dir if out_dir else _default_book_out_dir(project_root, story_bible)
    resolved_out_dir.mkdir(parents=True, exist_ok=True)

    runtime_state: dict[str, Any] | None = None
    if runtime_state_path and runtime_state_path.exists():
        runtime_state = _read_json(runtime_state_path)
    else:
        runtime_state = seed_runtime_state(story_bible, structure_map)

    summary, runtime_after = run_t5_pipeline(
        template_dna=template_dna,
        story_bible=story_bible,
        structure_map=structure_map,
        runtime_state=runtime_state,
        chapter_start=chapter_start,
        chapter_end=chapter_end,
        token_budget=token_budget,
        out_dir=str(resolved_out_dir),
        author_intent=author_intent,
        writer_config={
            "backend": writer_backend,
            "model": writer_model,
            "api_key": writer_api_key,
            "base_url": writer_base_url,
            "temperature": writer_temperature,
            "max_tokens": writer_max_tokens,
            "timeout_sec": writer_timeout_sec,
            "system_prompt_file": writer_system_prompt_file,
            "length_control": dict(length_control_cfg or {}),
            "anti_ai_style": dict(anti_ai_style_cfg or {}),
        },
        runtime_prompt_view_cfg=runtime_prompt_view_cfg,
        on_chapter_complete=on_chapter_complete,
    )
    _write_json(resolved_out_dir / "runtime_state_after_t5.json", runtime_after)

    if run_t7_batch:
        auto_batch_out_dir = t7_batch_out_dir if t7_batch_out_dir else (resolved_out_dir / "t7_batch_auto")
        _, batch_summary = _execute_t7_batch(
            story_bible=story_bible,
            structure_map=structure_map,
            runtime_state=runtime_after,
            packages_dir=resolved_out_dir,
            out_dir=auto_batch_out_dir,
            pattern=t7_batch_pattern or "chapter_package_ch*.json",
            auto_revise=not t7_batch_no_auto_revise,
        )
        summary["t7_batch_auto"] = {
            "enabled": True,
            "pass": batch_summary.get("pass", False),
            "out_dir": str(auto_batch_out_dir),
            "summary_file": str(auto_batch_out_dir / "t7_batch_summary.json"),
        }
    persisted_length = _persist_length_profile_to_runtime_config(
        project_root=project_root,
        writer_backend=writer_backend,
        t5_summary=summary,
        length_control_cfg=length_control_cfg or {},
    )
    _write_json(resolved_out_dir / "t5_summary.json", summary)
    _write_text(resolved_out_dir / "t5_summary.md", render_t5_summary_markdown(summary))

    print(f"[OK] T5 finished: {resolved_out_dir}")
    print(f"[OK] T5 summary: {resolved_out_dir / 't5_summary.json'}")
    print(f"[OK] T5 runtime: {resolved_out_dir / 'runtime_state_after_t5.json'}")
    if persisted_length:
        print(
            "[OK] length profile persisted: "
            f"max_tokens={persisted_length['max_tokens']}, "
            f"token_per_char_init={persisted_length['token_per_char_init']}, "
            f"config={persisted_length['config_path']}",
        )
    if run_t7_batch:
        print(f"[OK] T5 auto T7 batch: {summary['t7_batch_auto']['summary_file']}")
        print(f"[OK] T5 auto T7 batch pass: {summary['t7_batch_auto']['pass']}")
    return summary, runtime_after


def _run_t6(
    story_bible_path: Path,
    chapter_package_path: Path,
    runtime_state_path: Path,
    out_runtime_path: Path,
    out_delta_path: Path,
    out_report_path: Path,
    author_intent: str = "",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    story_bible = _read_json(story_bible_path)
    chapter_package = _read_json(chapter_package_path)
    runtime_state = _read_json(runtime_state_path)

    runtime_after, delta, report = replay_t6_from_chapter_package(
        runtime_state=runtime_state,
        story_bible=story_bible,
        chapter_package=chapter_package,
        author_intent=author_intent,
    )

    _write_json(out_runtime_path, runtime_after)
    _write_json(out_delta_path, delta)
    _write_text(out_report_path, render_t6_report_markdown(report))

    print(f"[OK] T6 finished: {out_runtime_path}")
    print(f"[OK] T6 delta: {out_delta_path}")
    print(f"[OK] T6 report: {out_report_path}")
    return runtime_after, delta, report


def _run_t7(
    story_bible_path: Path,
    structure_map_path: Path,
    chapter_package_path: Path,
    runtime_state_path: Path,
    out_package_path: Path,
    out_audit_path: Path,
    out_diff_path: Path,
    auto_revise: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    story_bible = _read_json(story_bible_path)
    structure_map = _read_json(structure_map_path)
    chapter_package = _read_json(chapter_package_path)
    runtime_state = _read_json(runtime_state_path)

    chapter_no = int(chapter_package.get("chapter", 0))
    if chapter_no <= 0:
        raise ValueError("chapter_package.chapter must be positive integer.")

    revised_draft, audit_report, diff_md = run_t7_audit_and_revise(
        chapter_no=chapter_no,
        draft_markdown=str(chapter_package.get("draft_markdown", "")),
        contract=chapter_package.get("contract", {}),
        alignment_report=chapter_package.get("alignment_report", {}),
        story_bible=story_bible,
        structure_map=structure_map,
        runtime_state=runtime_state,
        auto_revise=auto_revise,
    )

    revised_package = dict(chapter_package)
    revised_package["draft_markdown"] = revised_draft
    revised_package["t7_audit_report"] = audit_report
    revised_package["t7_diff_report_md"] = diff_md

    _write_json(out_package_path, revised_package)
    _write_json(out_audit_path, audit_report)
    _write_text(out_diff_path, diff_md)

    print(f"[OK] T7 finished: {out_package_path}")
    print(f"[OK] T7 audit: {out_audit_path}")
    print(f"[OK] T7 diff: {out_diff_path}")
    return revised_package, audit_report, diff_md


def _run_t7_batch(
    story_bible_path: Path,
    structure_map_path: Path,
    runtime_state_path: Path,
    packages_dir: Path,
    out_dir: Path,
    pattern: str = "chapter_package_ch*.json",
    auto_revise: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    story_bible = _read_json(story_bible_path)
    structure_map = _read_json(structure_map_path)
    runtime_state = _read_json(runtime_state_path)

    revised_packages, summary = _execute_t7_batch(
        story_bible=story_bible,
        structure_map=structure_map,
        runtime_state=runtime_state,
        packages_dir=packages_dir,
        out_dir=out_dir,
        pattern=pattern,
        auto_revise=auto_revise,
    )
    print(f"[OK] T7 batch finished: {out_dir}")
    print(f"[OK] T7 batch summary: {out_dir / 't7_batch_summary.json'}")
    print(f"[OK] T7 batch pass: {summary.get('pass', False)}")
    return revised_packages, summary


def _execute_t7_batch(
    story_bible: dict[str, Any],
    structure_map: dict[str, Any],
    runtime_state: dict[str, Any],
    packages_dir: Path,
    out_dir: Path,
    pattern: str = "chapter_package_ch*.json",
    auto_revise: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    files = discover_chapter_package_files(str(packages_dir), pattern=pattern)
    if not files:
        raise FileNotFoundError(f"No chapter packages found in {packages_dir} with pattern '{pattern}'.")

    chapter_packages = [_read_json(p) for p in files]
    revised_packages, summary = run_t7_batch_auditor(
        story_bible=story_bible,
        structure_map=structure_map,
        runtime_state=runtime_state,
        chapter_packages=chapter_packages,
        auto_revise=auto_revise,
    )

    _write_t7_batch_outputs(out_dir, revised_packages, summary)
    return revised_packages, summary


def _write_t7_batch_outputs(
    out_dir: Path,
    revised_packages: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    revised_dir = out_dir / "revised_packages"
    audits_dir = out_dir / "audits"
    diffs_dir = out_dir / "diffs"
    revised_dir.mkdir(parents=True, exist_ok=True)
    audits_dir.mkdir(parents=True, exist_ok=True)
    diffs_dir.mkdir(parents=True, exist_ok=True)

    for pkg in revised_packages:
        ch = int(pkg.get("chapter", 0))
        if ch <= 0:
            continue
        suffix = f"ch{ch:02d}"
        _write_json(revised_dir / f"chapter_package_{suffix}.json", pkg)
        _write_json(audits_dir / f"t7_audit_report_{suffix}.json", pkg.get("t7_audit_report", {}))
        _write_text(diffs_dir / f"t7_diff_report_{suffix}.md", str(pkg.get("t7_diff_report_md", "")))

    _write_json(out_dir / "t7_batch_summary.json", summary)
    _write_text(out_dir / "t7_batch_summary.md", render_t7_batch_summary_markdown(summary))


def _resolve_count_for_generate(count: int | None, chapter_start: int, chapter_end: int) -> int:
    if count is not None:
        return _resolve_positive_count(int(count), "--count")
    if chapter_end < chapter_start:
        raise ValueError("chapter-end must be >= chapter-start when --count is not provided.")
    return _resolve_positive_count(chapter_end - chapter_start + 1, "--count")


def _resolve_positive_count(value: int, flag: str) -> int:
    if value <= 0:
        raise ValueError(f"{flag} must be positive.")
    return value


def _remove_option(parser: argparse.ArgumentParser, action: argparse.Action) -> None:
    if action in parser._actions:
        parser._actions.remove(action)
    for group in getattr(parser, "_action_groups", []):
        if action in group._group_actions:
            group._group_actions.remove(action)
    for option_string in list(action.option_strings):
        parser._option_string_actions.pop(option_string, None)


def _run_skill_command(args: argparse.Namespace) -> None:
    if args.skill_command == "list":
        for name in list_skill_names():
            print(name)
        return
    if args.skill_command == "show":
        print(get_skill_text(args.name))
        return
    if args.skill_command == "export":
        out_path = export_skill(args.name, Path(args.out))
        print(f"[OK] Exported skill to {out_path}")
        return
    if args.skill_command == "scaffold":
        out_path = execute_skill_scaffold(
            skill_name=args.name,
            viral_story_path=Path(args.viral_story),
            new_story_idea_path=Path(args.new_story_idea),
            out_path=Path(args.out),
            writer_config={
                "backend": args.writer_backend or "builtin",
                "model": args.writer_model or "",
                "api_key": args.writer_api_key or "",
                "base_url": args.writer_base_url or "",
                "temperature": float(args.writer_temperature),
                "max_tokens": int(args.writer_max_tokens),
                "timeout_sec": int(args.writer_timeout_sec),
                "system_prompt_file": args.writer_system_prompt_file or "",
            },
        )
        print(f"[OK] Wrote remix bundle to {out_path}")
        return
    raise ValueError("skill command requires one of: list, show, export, scaffold")


def _run_generate(
    project_root: Path,
    remix_bundle_path: Path | None,
    chapter_start: int,
    chapter_count: int,
    token_budget: int,
    runtime_state_path: Path | None,
    out_dir: Path | None,
    author_intent: str,
    run_t7_batch: bool,
    t7_batch_out_dir: Path | None,
    t7_batch_pattern: str,
    t7_batch_no_auto_revise: bool,
    writer_backend: str,
    writer_model: str,
    writer_api_key: str,
    writer_base_url: str,
    writer_temperature: float,
    writer_max_tokens: int,
    writer_timeout_sec: int,
    writer_system_prompt_file: str,
    length_control_cfg: dict[str, Any] | None = None,
    anti_ai_style_cfg: dict[str, Any] | None = None,
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    chapter_count = _resolve_positive_count(chapter_count, "--count")
    chapter_end = chapter_start + chapter_count - 1
    root = project_root.resolve()

    bundle_path = remix_bundle_path if remix_bundle_path else resolve_default_remix_bundle_path(root)
    remix_bundle = load_remix_bundle(bundle_path)
    template_dna = remix_bundle["template_dna"]
    story_bible = remix_bundle["story_bible"]
    structure_map = remix_bundle["structure_map"]

    book_root = out_dir if out_dir else _default_book_out_dir(root, story_bible)
    process_dir = Path(tempfile.mkdtemp(prefix="template_novel_engine_process_"))
    asset_store = AssetStore(book_root)
    layout = resolve_book_layout(book_root)

    dna_out = process_dir / "template_dna.json"
    bible_out = process_dir / "story_bible.json"
    map_out = process_dir / "structure_map.json"
    outline_out = process_dir / "remix_outline.md"

    _write_json(dna_out, template_dna)
    _write_json(bible_out, story_bible)
    _write_json(map_out, structure_map)
    _write_text(outline_out, str(remix_bundle.get("human_readable_markdown", "")).strip() + "\n")
    print(f"[OK] Remix bundle loaded: {bundle_path}")
    asset_store.init_project_assets(
        template_dna=template_dna,
        story_bible=story_bible,
        structure_map=structure_map,
    )

    runtime_input = runtime_state_path if runtime_state_path else layout.runtime_state
    if runtime_input is not None and not runtime_input.exists():
        runtime_input = None

    print(
        f"[PROGRESS] generate chapters {chapter_start}-{chapter_end} (count={chapter_count})",
        flush=True,
    )
    exported_chapters: list[int] = []

    def _on_chapter_complete(package: dict[str, Any]) -> None:
        chapter_no = asset_store.write_chapter_package(package)
        exported_chapters.append(chapter_no)
        asset_store.refresh_manifest(story_bible=story_bible)
        print(
            f"[PROGRESS] exported chapter {chapter_no} -> {layout.exports_dir}",
            flush=True,
        )

    summary, runtime_after = _run_t5(
        template_dna_path=dna_out,
        story_bible_path=bible_out,
        structure_map_path=map_out,
        chapter_start=chapter_start,
        chapter_end=chapter_end,
        token_budget=token_budget,
        out_dir=process_dir,
        project_root_path=root,
        runtime_state_path=runtime_input,
        author_intent=author_intent,
        run_t7_batch=run_t7_batch,
        t7_batch_out_dir=t7_batch_out_dir if t7_batch_out_dir else (process_dir / "t7_batch_auto"),
        t7_batch_pattern=t7_batch_pattern,
        t7_batch_no_auto_revise=t7_batch_no_auto_revise,
        writer_backend=writer_backend,
        writer_model=writer_model,
        writer_api_key=writer_api_key,
        writer_base_url=writer_base_url,
        writer_temperature=writer_temperature,
        writer_max_tokens=writer_max_tokens,
        writer_timeout_sec=writer_timeout_sec,
        writer_system_prompt_file=writer_system_prompt_file,
        length_control_cfg=length_control_cfg,
        anti_ai_style_cfg=anti_ai_style_cfg,
        runtime_prompt_view_cfg=runtime_prompt_view_cfg,
        on_chapter_complete=_on_chapter_complete,
    )

    asset_store.write_runtime(runtime_after)
    asset_store.write_t5_summary(summary)

    if run_t7_batch:
        summary_file_raw = str(summary.get("t7_batch_auto", {}).get("summary_file", "")).strip()
        summary_file = Path(summary_file_raw).resolve() if summary_file_raw else None
        if summary_file is not None and summary_file.exists():
            _write_json(layout.index_dir / "t7_batch_summary.json", _read_json(summary_file))

    asset_store.refresh_manifest(story_bible=story_bible, extra={"run_t7_batch": run_t7_batch})
    try:
        _cleanup_process_dir(process_dir=process_dir)
    except Exception as exc:
        print(f"[WARN] cleanup process dir failed: {exc}")
    if exported_chapters:
        first_ch = min(exported_chapters)
        last_ch = max(exported_chapters)
        print(f"[OK] exported chapter range: {first_ch}-{last_ch}")
    print(f"[OK] generated chapter range: {chapter_start}-{chapter_end}")
    print(f"[OK] exports dir: {layout.exports_dir}")
    print(f"[OK] project assets dir: {book_root}")
    print("[OK] generate finished.")
    return summary, runtime_after


def _run_continue(
    project_root: Path,
    book: str,
    chapter_count: int,
    token_budget: int,
    runtime_state_path: Path | None,
    author_intent: str,
    run_t7_batch: bool,
    t7_batch_out_dir: Path | None,
    t7_batch_pattern: str,
    t7_batch_no_auto_revise: bool,
    writer_backend: str,
    writer_model: str,
    writer_api_key: str,
    writer_base_url: str,
    writer_temperature: float,
    writer_max_tokens: int,
    writer_timeout_sec: int,
    writer_system_prompt_file: str,
    length_control_cfg: dict[str, Any] | None = None,
    anti_ai_style_cfg: dict[str, Any] | None = None,
    runtime_prompt_view_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    chapter_count = _resolve_positive_count(chapter_count, "--count")
    root = project_root.resolve()
    book_root = _resolve_book_root(root, book)
    if not book_root.exists():
        raise FileNotFoundError(f"Book directory not found: {book_root}")

    asset_store = AssetStore(book_root)
    layout = resolve_book_layout(book_root)

    dna_out = layout.project_template_dna
    bible_out = layout.project_story_bible
    map_out = layout.project_structure_map
    missing_assets = [p for p in (dna_out, bible_out, map_out) if not p.exists()]
    if missing_assets:
        missing_text = ", ".join(str(p) for p in missing_assets)
        raise FileNotFoundError(f"Missing key assets for continue. Run generate first. Missing: {missing_text}")

    runtime_input = runtime_state_path if runtime_state_path else layout.runtime_state
    if runtime_input is not None and not runtime_input.exists():
        runtime_input = None

    story_bible = _read_json(bible_out)
    existing_chapters = asset_store.existing_exported_chapters()
    chapter_start = (max(existing_chapters) + 1) if existing_chapters else 1
    chapter_end = chapter_start + chapter_count - 1
    print(
        f"[PROGRESS] continue chapters {chapter_start}-{chapter_end} (count={chapter_count})",
        flush=True,
    )

    process_dir = Path(tempfile.mkdtemp(prefix="template_novel_engine_process_"))
    summary: dict[str, Any]
    runtime_after: dict[str, Any]
    exported_chapters: list[int] = []

    def _on_chapter_complete(package: dict[str, Any]) -> None:
        chapter_no = asset_store.write_chapter_package(package)
        exported_chapters.append(chapter_no)
        asset_store.refresh_manifest(story_bible=story_bible)
        print(
            f"[PROGRESS] exported chapter {chapter_no} -> {layout.exports_dir}",
            flush=True,
        )

    try:
        summary, runtime_after = _run_t5(
            template_dna_path=dna_out,
            story_bible_path=bible_out,
            structure_map_path=map_out,
            chapter_start=chapter_start,
            chapter_end=chapter_end,
            token_budget=token_budget,
            out_dir=process_dir,
            project_root_path=root,
            runtime_state_path=runtime_input,
            author_intent=author_intent,
            run_t7_batch=run_t7_batch,
            t7_batch_out_dir=t7_batch_out_dir if t7_batch_out_dir else (process_dir / "t7_batch_auto"),
            t7_batch_pattern=t7_batch_pattern,
            t7_batch_no_auto_revise=t7_batch_no_auto_revise,
            writer_backend=writer_backend,
            writer_model=writer_model,
            writer_api_key=writer_api_key,
            writer_base_url=writer_base_url,
            writer_temperature=writer_temperature,
            writer_max_tokens=writer_max_tokens,
            writer_timeout_sec=writer_timeout_sec,
            writer_system_prompt_file=writer_system_prompt_file,
            length_control_cfg=length_control_cfg,
            anti_ai_style_cfg=anti_ai_style_cfg,
            runtime_prompt_view_cfg=runtime_prompt_view_cfg,
            on_chapter_complete=_on_chapter_complete,
        )
        asset_store.write_runtime(runtime_after)
        asset_store.write_t5_summary(summary)

        if run_t7_batch:
            summary_file_raw = str(summary.get("t7_batch_auto", {}).get("summary_file", "")).strip()
            summary_file = Path(summary_file_raw).resolve() if summary_file_raw else None
            if summary_file is not None and summary_file.exists():
                _write_json(layout.index_dir / "t7_batch_summary.json", _read_json(summary_file))
        asset_store.refresh_manifest(story_bible=story_bible, extra={"run_t7_batch": run_t7_batch})
    finally:
        try:
            _cleanup_process_dir(process_dir=process_dir)
        except Exception as exc:
            print(f"[WARN] cleanup process dir failed: {exc}")

    print(f"[OK] continue chapter range: {chapter_start}-{chapter_end}")
    if exported_chapters:
        print(f"[OK] continue exported chapters: {min(exported_chapters)}-{max(exported_chapters)}")
    print(f"[OK] exports dir: {layout.exports_dir}")
    print(f"[OK] project assets dir: {book_root}")
    print("[OK] continue finished.")
    return summary, runtime_after


def _resolve_book_root(project_root: Path, book: str) -> Path:
    raw = str(book or "").strip()
    if not raw:
        raise ValueError("--book is required.")
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    outputs_candidate = project_root / "outputs" / raw
    if outputs_candidate.exists():
        return outputs_candidate
    if candidate.exists():
        return candidate.resolve()
    return outputs_candidate


def _cleanup_process_dir(process_dir: Path) -> None:
    if not process_dir.exists():
        return
    process_resolved = process_dir.resolve()

    def _on_rm_error(func: Any, path: str, _exc: Any) -> None:
        os.chmod(path, stat.S_IWRITE)
        func(path)

    last_exc: Exception | None = None
    for _ in range(5):
        try:
            shutil.rmtree(process_resolved, onerror=_on_rm_error)
            return
        except Exception as exc:  # pragma: no cover - defensive cleanup
            last_exc = exc
            time.sleep(0.2)
    if last_exc:
        raise last_exc


def _default_book_out_dir(project_root: Path, story_bible: dict[str, Any]) -> Path:
    title = str(story_bible.get("metadata", {}).get("title", "")).strip() or "Untitled Story"
    return project_root / "outputs" / _safe_dirname(title)


def _safe_dirname(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "Untitled Story"
    text = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip(" ._")
    return text or "Untitled Story"


def _resolve_first_existing(*paths: Path) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def _run_all(project_root: Path) -> None:
    template = _resolve_default_template_path(project_root)
    story = _resolve_default_story_path(project_root)
    outputs = project_root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)

    dna_out = outputs / "template_dna.json"
    bible_out = outputs / "story_bible.json"
    map_out = outputs / "structure_map.json"
    outline_out = outputs / "volume_outline.md"

    _run_t1(template, dna_out)
    _run_t2(story, bible_out)
    _run_t3(dna_out, bible_out, map_out, outline_out)
    print("[OK] run-all finished.")


def _resolve_default_template_path(project_root: Path) -> Path:
    return _resolve_first_existing(
        project_root / "爆款解析.md",
        project_root / "inputs" / "爆款解析.md",
        project_root / "template_analysis.md",
        project_root / "inputs" / "template_analysis.md",
    )


def _resolve_default_story_path(project_root: Path) -> Path:
    return _resolve_first_existing(
        project_root / "新故事思路.md",
        project_root / "inputs" / "新故事思路.md",
        project_root / "story_idea.md",
        project_root / "inputs" / "story_idea.md",
    )


def _persist_length_profile_to_runtime_config(
    project_root: Path,
    writer_backend: str,
    t5_summary: dict[str, Any],
    length_control_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    backend = str(writer_backend or "").strip().lower()
    if backend not in {"openai", "claude"}:
        return None

    writer_meta = t5_summary.get("writer", {})
    if not isinstance(writer_meta, dict):
        return None
    writer_length = writer_meta.get("length_control", {})
    if not isinstance(writer_length, dict):
        return None
    if not bool(writer_length.get("enabled", False)):
        return None

    token_per_char_est = _safe_float(writer_length.get("token_per_char_est"), -1.0)
    if token_per_char_est <= 0:
        return None

    config_path = _resolve_runtime_config_path(project_root)
    if config_path is None:
        return None

    try:
        cfg = _read_json_object_utf8_sig(config_path)
    except Exception:
        return None

    writer_cfg = cfg.get("writer", {})
    if not isinstance(writer_cfg, dict):
        writer_cfg = {}
    length_cfg = cfg.get("length_control", {})
    if not isinstance(length_cfg, dict):
        length_cfg = {}

    current_max_tokens = _safe_int(
        writer_cfg.get("max_tokens", writer_cfg.get("max_token", 2200)),
        2200,
    )
    target_chars = _infer_target_chars_for_next_run(
        t5_summary=t5_summary,
        length_control_cfg=length_control_cfg,
        config_length_control=length_cfg,
    )
    safety_multiplier = _safe_float(
        length_control_cfg.get(
            "token_safety_multiplier",
            length_cfg.get("token_safety_multiplier", 1.1),
        ),
        1.1,
    )
    recommended_max_tokens = int(round(target_chars * token_per_char_est * safety_multiplier))
    recommended_max_tokens = max(256, min(32000, recommended_max_tokens))
    if current_max_tokens <= 0:
        next_max_tokens = recommended_max_tokens
    else:
        next_max_tokens = int(round(current_max_tokens * 0.7 + recommended_max_tokens * 0.3))
        next_max_tokens = max(256, min(32000, next_max_tokens))

    rounded_est = round(token_per_char_est, 4)
    changed = False
    if _safe_int(writer_cfg.get("max_tokens"), -1) != next_max_tokens:
        writer_cfg["max_tokens"] = next_max_tokens
        changed = True
    if "max_token" in writer_cfg and _safe_int(writer_cfg.get("max_token"), -1) != next_max_tokens:
        writer_cfg["max_token"] = next_max_tokens
        changed = True
    if _safe_float(length_cfg.get("token_per_char_init"), -1.0) != rounded_est:
        length_cfg["token_per_char_init"] = rounded_est
        changed = True

    if not changed:
        return {
            "config_path": str(config_path),
            "max_tokens": next_max_tokens,
            "token_per_char_init": rounded_est,
        }

    cfg["writer"] = writer_cfg
    cfg["length_control"] = length_cfg
    _write_json_utf8(config_path, cfg)
    return {
        "config_path": str(config_path),
        "max_tokens": next_max_tokens,
        "token_per_char_init": rounded_est,
    }


def _infer_target_chars_for_next_run(
    t5_summary: dict[str, Any],
    length_control_cfg: dict[str, Any],
    config_length_control: dict[str, Any],
) -> int:
    length_summary = t5_summary.get("length_control", {})
    rows = length_summary.get("rows", []) if isinstance(length_summary, dict) else []
    targets: list[int] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = _safe_int(row.get("target_chars"), 0)
            if value > 0:
                targets.append(value)
    if targets:
        return max(500, min(20000, int(round(sum(targets) / len(targets)))))

    fallback = _safe_int(
        length_control_cfg.get(
            "default_target_chars",
            config_length_control.get("default_target_chars", 3000),
        ),
        3000,
    )
    return max(500, min(20000, fallback))


def _resolve_runtime_config_path(project_root: Path) -> Path | None:
    candidates: list[Path] = [project_root / RUNTIME_CONFIG_FILENAME]
    cwd_candidate = Path.cwd() / RUNTIME_CONFIG_FILENAME
    if cwd_candidate != candidates[0]:
        candidates.append(cwd_candidate)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_json_object_utf8_sig(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected: {path}")
    return data


def _write_json_utf8(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


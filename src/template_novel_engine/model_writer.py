from __future__ import annotations

import json
from pathlib import Path
import re
import time
from typing import Any
from urllib import error, request

from .anti_ai_style import normalize_policy
from .prompt_templates import (
    DEFAULT_SYSTEM_PROMPT,
    build_chapter_prompt_payload,
    chapter_generation_extra_constraints,
)


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
SUPPORTED_BACKENDS = {"builtin", "openai", "claude"}

_CHAPTER_BLOCK_RE = re.compile(r"<chapter_markdown>\s*(.*?)\s*</chapter_markdown>", re.IGNORECASE | re.DOTALL)
_SUMMARY_BLOCK_RE = re.compile(r"<chapter_summary>\s*(.*?)\s*</chapter_summary>", re.IGNORECASE | re.DOTALL)

DEFAULT_LENGTH_CONTROL_CONFIG = {
    "enabled": True,
    "default_target_chars": 3000,
    "tolerance_ratio": 0.15,
    "auto_revise_on_out_of_range": True,
    "max_revise_rounds": 1,
    "token_per_char_est": 0.9,
    "token_per_char_min": 0.4,
    "token_per_char_max": 1.8,
    "token_safety_multiplier": 1.1,
}

def normalize_length_control_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(DEFAULT_LENGTH_CONTROL_CONFIG)
    incoming = dict(raw or {})
    cfg.update(incoming)
    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["auto_revise_on_out_of_range"] = bool(cfg.get("auto_revise_on_out_of_range", True))
    cfg["default_target_chars"] = max(500, int(cfg.get("default_target_chars", 3000)))
    cfg["tolerance_ratio"] = min(0.45, max(0.05, float(cfg.get("tolerance_ratio", 0.15))))
    cfg["max_revise_rounds"] = max(0, min(3, int(cfg.get("max_revise_rounds", 1))))
    cfg["token_per_char_min"] = min(2.5, max(0.1, float(cfg.get("token_per_char_min", 0.4))))
    cfg["token_per_char_max"] = min(3.5, max(cfg["token_per_char_min"], float(cfg.get("token_per_char_max", 1.8))))
    cfg["token_per_char_est"] = min(
        cfg["token_per_char_max"],
        max(cfg["token_per_char_min"], float(cfg.get("token_per_char_est", cfg.get("token_per_char_init", 0.9)))),
    )
    cfg["token_safety_multiplier"] = min(2.0, max(1.0, float(cfg.get("token_safety_multiplier", 1.1))))
    return cfg


def normalize_writer_config(writer_config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(writer_config or {})
    length_control = normalize_length_control_config(cfg.get("length_control", {}))
    backend = str(cfg.get("backend", "builtin")).strip().lower()
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"Unsupported writer backend: {backend}. Choose from {sorted(SUPPORTED_BACKENDS)}.")

    if backend == "builtin":
        builtin_length_control = dict(length_control)
        builtin_length_control["enabled"] = False
        return {
            "backend": "builtin",
            "model": "rule-template-v1",
            "temperature": 0.0,
            "max_tokens": 0,
            "timeout_sec": 0,
            "base_url": "",
            "api_key": "",
            "system_prompt": str(cfg.get("system_prompt", "")).strip(),
            "anti_ai_style": normalize_policy(cfg.get("anti_ai_style", {})),
            "length_control": builtin_length_control,
        }

    model = str(cfg.get("model", "")).strip()
    if not model:
        raise ValueError(f"{backend} writer requires model. Pass --writer-model or set it in config file.")

    api_key = str(cfg.get("api_key", "")).strip()
    if not api_key:
        raise ValueError(f"{backend} writer requires API key. Pass --writer-api-key or set it in config file.")

    base_url = str(cfg.get("base_url", "")).strip()
    if not base_url:
        base_url = DEFAULT_OPENAI_BASE_URL if backend == "openai" else DEFAULT_ANTHROPIC_BASE_URL

    temperature = float(cfg.get("temperature", 0.7))
    max_tokens = int(cfg.get("max_tokens", 2200))
    timeout_sec = int(cfg.get("timeout_sec", 120))
    if max_tokens <= 0:
        raise ValueError("writer max_tokens must be positive.")
    if timeout_sec <= 0:
        raise ValueError("writer timeout_sec must be positive.")
    retries = int(cfg.get("retries", 3))
    retry_backoff_sec = float(cfg.get("retry_backoff_sec", 2.0))
    stream = bool(cfg.get("stream", True))
    if retries < 0:
        raise ValueError("writer retries must be >= 0.")
    if retry_backoff_sec < 0:
        raise ValueError("writer retry_backoff_sec must be >= 0.")

    system_prompt = str(cfg.get("system_prompt", "")).strip()
    system_prompt_file = str(cfg.get("system_prompt_file", "")).strip()
    if system_prompt_file:
        prompt_path = Path(system_prompt_file)
        if not prompt_path.exists():
            raise FileNotFoundError(f"writer system prompt file not found: {prompt_path}")
        system_prompt = prompt_path.read_text(encoding="utf-8").strip()

    return {
        "backend": backend,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout_sec": timeout_sec,
        "retries": retries,
        "retry_backoff_sec": retry_backoff_sec,
        "stream": stream,
        "system_prompt": system_prompt or DEFAULT_SYSTEM_PROMPT,
        "anti_ai_style": normalize_policy(cfg.get("anti_ai_style", {})),
        "length_control": length_control,
    }


def writer_public_profile(writer_config: dict[str, Any]) -> dict[str, Any]:
    length_cfg = normalize_length_control_config(writer_config.get("length_control", {}))
    return {
        "backend": str(writer_config.get("backend", "builtin")),
        "model": str(writer_config.get("model", "")),
        "temperature": float(writer_config.get("temperature", 0.0)),
        "max_tokens": int(writer_config.get("max_tokens", 0)),
        "base_url": str(writer_config.get("base_url", "")),
        "retries": int(writer_config.get("retries", 0)),
        "retry_backoff_sec": float(writer_config.get("retry_backoff_sec", 0.0)),
        "stream": bool(writer_config.get("stream", True)),
        "anti_ai_style_enabled": bool(normalize_policy(writer_config.get("anti_ai_style", {})).get("enabled", True)),
        "length_control": {
            "enabled": bool(length_cfg.get("enabled", True)),
            "tolerance_ratio": float(length_cfg.get("tolerance_ratio", 0.15)),
            "token_per_char_est": float(length_cfg.get("token_per_char_est", 0.9)),
        },
    }


def generate_text_with_llm(
    *,
    writer_config: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, dict[str, Any]]:
    cfg = normalize_writer_config(writer_config)
    backend = cfg["backend"]
    if backend not in {"openai", "claude"}:
        raise ValueError(f"LLM text generation requires backend openai/claude, got {backend}")

    started = time.time()
    raw_text, usage = _call_backend(backend, cfg, system_prompt, user_prompt)
    latency_ms = int((time.time() - started) * 1000)
    meta = {
        "backend": backend,
        "model": cfg.get("model", ""),
        "latency_ms": latency_ms,
        "usage": usage if isinstance(usage, dict) else {},
    }
    return raw_text, meta


def generate_chapter_draft_with_llm(
    template_dna: dict[str, Any],
    story_bible: dict[str, Any],
    contract: dict[str, Any],
    context_bundle: dict[str, Any],
    chapter_no: int,
    writer_config: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    cfg = normalize_writer_config(writer_config)
    backend = cfg["backend"]
    if backend not in {"openai", "claude"}:
        raise ValueError(f"LLM generation requires backend openai/claude, got {backend}")

    length_cfg = normalize_length_control_config(cfg.get("length_control", {}))
    target_chars, min_chars, max_chars, tolerance_ratio = _resolve_length_target(story_bible, contract, length_cfg)

    system_prompt, user_prompt = build_chapter_prompts(
        template_dna=template_dna,
        story_bible=story_bible,
        contract=contract,
        context_bundle=context_bundle,
        chapter_no=chapter_no,
        system_prompt_override=cfg.get("system_prompt", ""),
        anti_ai_style_cfg=cfg.get("anti_ai_style", {}),
        precheck=context_bundle.get("precheck", {}),
    )

    per_call: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {}
    revise_triggered = False

    first_cfg = _cfg_with_dynamic_max_tokens(cfg, target_chars, length_cfg)
    started = time.time()
    raw_text, usage = _call_backend(backend, first_cfg, system_prompt, user_prompt)
    latency_ms = int((time.time() - started) * 1000)

    draft_markdown, chapter_summary = _parse_model_output(raw_text, contract, chapter_no)
    usage_total = _merge_usage(usage_total, usage)
    actual_chars = _count_chapter_chars(draft_markdown)
    within_range = min_chars <= actual_chars <= max_chars
    per_call.append(
        {
            "attempt": 1,
            "mode": "initial",
            "max_tokens": int(first_cfg.get("max_tokens", cfg.get("max_tokens", 0))),
            "actual_chars": actual_chars,
            "within_range": within_range,
        },
    )
    _update_token_per_char_est(length_cfg, usage, actual_chars)

    if (
        bool(length_cfg.get("enabled", True))
        and bool(length_cfg.get("auto_revise_on_out_of_range", True))
        and not within_range
    ):
        max_revise_rounds = int(length_cfg.get("max_revise_rounds", 1))
        for idx in range(max_revise_rounds):
            revise_triggered = True
            revise_round = idx + 1
            revise_system, revise_user = _build_length_revise_prompts(
                contract=contract,
                chapter_markdown=draft_markdown,
                chapter_summary=chapter_summary,
                target_chars=target_chars,
                min_chars=min_chars,
                max_chars=max_chars,
                tolerance_ratio=tolerance_ratio,
                chapter_no=chapter_no,
            )
            revise_cfg = _cfg_with_dynamic_max_tokens(cfg, target_chars, length_cfg)
            started_revise = time.time()
            raw_revise, revise_usage = _call_backend(backend, revise_cfg, revise_system, revise_user)
            latency_ms += int((time.time() - started_revise) * 1000)
            new_markdown, new_summary = _parse_model_output(raw_revise, contract, chapter_no)
            new_chars = _count_chapter_chars(new_markdown)
            usage_total = _merge_usage(usage_total, revise_usage)
            _update_token_per_char_est(length_cfg, revise_usage, new_chars)

            draft_markdown = new_markdown
            chapter_summary = new_summary
            actual_chars = new_chars
            within_range = min_chars <= actual_chars <= max_chars
            per_call.append(
                {
                    "attempt": revise_round + 1,
                    "mode": "length_revise",
                    "max_tokens": int(revise_cfg.get("max_tokens", cfg.get("max_tokens", 0))),
                    "actual_chars": actual_chars,
                    "within_range": within_range,
                },
            )
            if within_range:
                break

    meta = {
        "backend": backend,
        "model": cfg.get("model", ""),
        "latency_ms": latency_ms,
        "usage": usage_total,
        "length_control": {
            "enabled": bool(length_cfg.get("enabled", True)),
            "target_chars": target_chars,
            "min_chars": min_chars,
            "max_chars": max_chars,
            "tolerance_ratio": tolerance_ratio,
            "actual_chars": actual_chars,
            "within_range": within_range,
            "auto_revise_triggered": revise_triggered,
            "attempts": len(per_call),
            "token_per_char_est": float(length_cfg.get("token_per_char_est", 0.9)),
            "calls": per_call,
        },
    }
    return draft_markdown, chapter_summary, meta


def build_chapter_prompts(
    template_dna: dict[str, Any],
    story_bible: dict[str, Any],
    contract: dict[str, Any],
    context_bundle: dict[str, Any],
    chapter_no: int,
    system_prompt_override: str = "",
    anti_ai_style_cfg: dict[str, Any] | None = None,
    precheck: dict[str, Any] | None = None,
) -> tuple[str, str]:
    prompt_payload = build_chapter_prompt_payload(
        contract=contract,
        context_bundle=context_bundle,
        precheck=precheck or {},
        anti_ai_style_cfg=anti_ai_style_cfg,
    )
    system_prompt = system_prompt_override.strip() or prompt_payload["system_prompt"]

    metadata = story_bible.get("metadata", {})
    premise = story_bible.get("premise", {})
    conflicts = story_bible.get("conflicts", {})
    world = story_bible.get("world", {})
    constraints = story_bible.get("constraints", {})

    characters = story_bible.get("characters", [])
    char_lines = []
    for ch in characters[:8]:
        char_lines.append(
            f"- {ch.get('name', '')} | role={ch.get('role', '')} | goal={ch.get('goal', '')} | flaw={ch.get('flaw', '')} | arc={ch.get('arc', '')}",
        )
    if not char_lines:
        char_lines.append("- (none)")

    template_formulas = _render_list(template_dna.get("template_formulas", []), limit=6)
    dialogue_patterns = _render_dialogue_patterns(template_dna.get("dialogue_patterns", []), limit=8)
    principles = _render_list(_normalize_principles(template_dna.get("principles", [])), limit=8)
    motifs = _render_list(template_dna.get("reusable_motifs", []), limit=10)
    stage_anchor = _render_stage_anchor(template_dna, contract)

    context_full = str(context_bundle.get("prompt_blocks", {}).get("full_context", "")).strip()
    context_full = context_full or "(empty)"

    chapter_title = str(contract.get("chapter_title", f"Chapter {chapter_no}")).strip()
    chapter_objective = str(contract.get("chapter_objective", "")).strip()
    stage_goal = str(contract.get("stage_goal", "")).strip()
    escalation = str(contract.get("escalation_target", "")).strip()
    must_keep = _render_list(contract.get("must_keep", []), limit=8)
    forbidden = _render_list(contract.get("forbidden", []), limit=8)
    planned_beats = _render_list(contract.get("planned_beats", []), limit=8)
    chapter_word_target = _safe_int(
        contract.get("chapter_word_target", metadata.get("chapter_word_target", 2200)),
        2200,
    )
    chapter_word_target = max(500, min(12000, chapter_word_target))
    tolerance_ratio = _safe_float(
        contract.get("chapter_word_tolerance_ratio", metadata.get("chapter_word_tolerance_ratio", 0.15)),
        0.15,
    )
    tolerance_ratio = min(0.45, max(0.05, tolerance_ratio))
    tolerance_pct = int(round(tolerance_ratio * 100))
    structured_payload = prompt_payload["user_prompt"].strip()

    user_prompt = f"""你要写第 {chapter_no} 章，使用“模板结构”驱动“原创内容”。

[StructuredChapterPayload]
{structured_payload}

[TemplateDNA]
- Core premise: {template_dna.get('core_premise', '')}
- Stage anchor for this chapter: {stage_anchor}
- Template formulas:
{template_formulas}
- Dialogue patterns:
{dialogue_patterns}
- Principles:
{principles}
- Reusable motifs:
{motifs}

[StoryBible]
- Title: {metadata.get('title', '')}
- Genre: {metadata.get('genre', '')}
- Tone: {metadata.get('tone', '')}
- Premise(logline): {premise.get('logline', '')}
- Theme: {premise.get('theme', '')}
- Main conflict: {conflicts.get('main_conflict', '')}
- Secondary conflicts: {', '.join(conflicts.get('secondary_conflicts', []))}
- World era: {world.get('era', '')}
- World locations: {', '.join(world.get('locations', []))}
- World power system: {world.get('power_system', '')}
- World rules: {', '.join(world.get('rules', [])[:10])}
- Characters:
{chr(10).join(char_lines)}
- Constraints must_have: {', '.join(constraints.get('must_have', []))}
- Constraints must_avoid: {', '.join(constraints.get('must_avoid', []))}

[ChapterContract]
- Chapter title: {chapter_title}
- Stage id: {contract.get('stage_id', '')}
- Stage range: {contract.get('stage_range', {}).get('chapter_start', '')}-{contract.get('stage_range', {}).get('chapter_end', '')}
- Template anchor: {contract.get('template_anchor', '')}
- Chapter objective: {chapter_objective}
- Stage goal: {stage_goal}
- Escalation target: {escalation}
- Must keep:
{must_keep}
- Forbidden:
{forbidden}
- Planned beats:
{planned_beats}

[ComposedContextFromT4]
{context_full}

[HardRequirements]
1) 写原创章节，不可复写模板原文句子，不可照搬现成 IP 情节。
2) 章节必须体现本章 objective，并且最后抛出下一章压力点。
3) 主角必须有“主动决策”。
4) 至少体现一次信息增量/反转/推进，不允许空转。
5) 严禁输出 TODO/TBD/待补/......。
6) 章节长度目标：约 {chapter_word_target} 字（可上下浮动 {tolerance_pct}%）。
7) 必须包含“## 本章模板对齐点”小节，并给出阶段、结构任务、阶段目标、升级目标。
8) 严禁使用“总之/综上所述/首先/其次/最后/接上回/书接上文”等模板化过渡语。

[OutputFormat]
严格按以下标签输出，不要输出额外解释：
<chapter_markdown>
# {chapter_title}

## 正文
（这里是章节正文）

## 本章模板对齐点
- 阶段: ...
- 结构任务: ...
- 阶段目标: ...
- 升级目标: ...
</chapter_markdown>
<chapter_summary>一句话总结本章推进结果（30-90字）</chapter_summary>
    """
    return system_prompt, user_prompt


def _call_backend(
    backend: str,
    cfg: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, dict[str, Any]]:
    if backend == "openai":
        return _call_openai_chat_completion(cfg, system_prompt, user_prompt)
    if backend == "claude":
        return _call_anthropic_messages(cfg, system_prompt, user_prompt)
    raise ValueError(f"Unsupported backend for llm call: {backend}")


def _resolve_length_target(
    story_bible: dict[str, Any],
    contract: dict[str, Any],
    length_cfg: dict[str, Any],
) -> tuple[int, int, int, float]:
    metadata = story_bible.get("metadata", {})
    target_chars = _safe_int(
        contract.get("chapter_word_target", metadata.get("chapter_word_target", length_cfg.get("default_target_chars", 3000))),
        int(length_cfg.get("default_target_chars", 3000)),
    )
    target_chars = max(500, min(20000, target_chars))
    tolerance_ratio = _safe_float(
        contract.get("chapter_word_tolerance_ratio", metadata.get("chapter_word_tolerance_ratio", length_cfg.get("tolerance_ratio", 0.15))),
        float(length_cfg.get("tolerance_ratio", 0.15)),
    )
    tolerance_ratio = min(0.45, max(0.05, tolerance_ratio))
    min_chars = max(200, int(round(target_chars * (1 - tolerance_ratio))))
    max_chars = max(min_chars + 50, int(round(target_chars * (1 + tolerance_ratio))))
    return target_chars, min_chars, max_chars, tolerance_ratio


def _cfg_with_dynamic_max_tokens(
    cfg: dict[str, Any],
    target_chars: int,
    length_cfg: dict[str, Any],
) -> dict[str, Any]:
    out = dict(cfg)
    est = _safe_float(length_cfg.get("token_per_char_est", 0.9), 0.9)
    multiplier = _safe_float(length_cfg.get("token_safety_multiplier", 1.1), 1.1)
    dynamic_max_tokens = int(round(target_chars * est * multiplier))
    dynamic_max_tokens = max(256, dynamic_max_tokens)
    hard_cap = _safe_int(cfg.get("max_tokens", 2200), 2200)
    if hard_cap > 0:
        dynamic_max_tokens = min(dynamic_max_tokens, hard_cap)
        dynamic_max_tokens = max(64, dynamic_max_tokens)
    out["max_tokens"] = dynamic_max_tokens
    return out


def _build_length_revise_prompts(
    contract: dict[str, Any],
    chapter_markdown: str,
    chapter_summary: str,
    target_chars: int,
    min_chars: int,
    max_chars: int,
    tolerance_ratio: float,
    chapter_no: int,
) -> tuple[str, str]:
    title = str(contract.get("chapter_title", f"Chapter {chapter_no}")).strip()
    tolerance_pct = int(round(tolerance_ratio * 100))
    system_prompt = (
        "你是中文网文章节修订器。目标是修正字数，不改变事实链、角色动机和章节关键事件。"
        "输出必须使用 <chapter_markdown> 与 <chapter_summary> 标签。"
    )
    user_prompt = f"""请对下列章节做一次字数定向修订。

[LengthTarget]
- target_chars: {target_chars}
- allowed_range: {min_chars}-{max_chars}
- tolerance: ±{tolerance_pct}%

[Constraints]
1) 保持本章主要事件、冲突方向、结尾压力点不变。
2) 保持“## 本章模板对齐点”小节存在。
3) 不输出 TODO/TBD/待补 等占位符。
4) 若当前偏长则压缩冗余描写；若偏短则补充动作细节与情绪推进。

[CurrentChapter]
{chapter_markdown}

[CurrentSummary]
{chapter_summary}

[OutputFormat]
<chapter_markdown>
# {title}
## 正文
（修订后的正文）
## 本章模板对齐点
- 阶段: ...
- 结构任务: ...
- 阶段目标: ...
- 升级目标: ...
</chapter_markdown>
<chapter_summary>一句话总结本章推进结果（30-90字）</chapter_summary>
"""
    return system_prompt, user_prompt


def _count_chapter_chars(chapter_markdown: str) -> int:
    body = _strip_alignment_section(chapter_markdown or "")
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


def _merge_usage(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base or {})
    for key, value in (extra or {}).items():
        if isinstance(value, (int, float)):
            out[key] = int(_safe_int(out.get(key, 0), 0) + int(value))
        else:
            if key not in out:
                out[key] = value
    return out


def _extract_completion_tokens(usage: dict[str, Any]) -> int:
    if not isinstance(usage, dict):
        return 0
    for key in ("completion_tokens", "output_tokens", "generated_tokens"):
        if key in usage:
            return max(0, _safe_int(usage.get(key, 0), 0))
    return 0


def _update_token_per_char_est(length_cfg: dict[str, Any], usage: dict[str, Any], actual_chars: int) -> None:
    completion_tokens = _extract_completion_tokens(usage)
    if completion_tokens <= 0 or actual_chars <= 0:
        return
    ratio = completion_tokens / actual_chars
    ratio = min(float(length_cfg.get("token_per_char_max", 1.8)), max(float(length_cfg.get("token_per_char_min", 0.4)), ratio))
    prev = _safe_float(length_cfg.get("token_per_char_est", 0.9), 0.9)
    length_cfg["token_per_char_est"] = round(prev * 0.7 + ratio * 0.3, 4)


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


def _call_openai_chat_completion(
    cfg: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, dict[str, Any]]:
    if bool(cfg.get("stream", True)):
        try:
            return _call_openai_chat_completion_stream(cfg, system_prompt, user_prompt)
        except RuntimeError as exc:
            # Fall through to non-stream path for provider compatibility.
            print(f"[WARN] LLM stream path failed, fallback to non-stream: {exc}", flush=True)

    url = _join_api_url(str(cfg.get("base_url", "")), "/chat/completions")
    payload = {
        "model": str(cfg.get("model", "")),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(cfg.get("temperature", 0.7)),
        "max_tokens": int(cfg.get("max_tokens", 2200)),
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.get('api_key', '')}",
    }
    try:
        resp = _http_post_json(
            url=url,
            headers=headers,
            payload=payload,
            timeout_sec=int(cfg.get("timeout_sec", 120)),
            retries=int(cfg.get("retries", 3)),
            retry_backoff_sec=float(cfg.get("retry_backoff_sec", 2.0)),
        )
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 504" in message or "HTTP 503" in message or "HTTP 500" in message or "Timeout calling LLM API" in message:
            print(f"[WARN] LLM chat/completions unstable, fallback to /responses: {message}", flush=True)
            return _call_openai_responses(cfg, system_prompt, user_prompt)
        raise
    text = _extract_openai_text(resp)
    if not text.strip():
        # Some gateways return empty content for reasoning-first models on chat/completions.
        # Fallback to /responses keeps compatibility with OpenAI-style proxy providers.
        print("[WARN] LLM chat/completions returned empty content, fallback to /responses.", flush=True)
        return _call_openai_responses(cfg, system_prompt, user_prompt)
    usage = resp.get("usage", {}) if isinstance(resp, dict) else {}
    return text, usage if isinstance(usage, dict) else {}


def _call_openai_chat_completion_stream(
    cfg: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, dict[str, Any]]:
    url = _join_api_url(str(cfg.get("base_url", "")), "/chat/completions")
    payload = {
        "model": str(cfg.get("model", "")),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(cfg.get("temperature", 0.7)),
        "max_tokens": int(cfg.get("max_tokens", 2200)),
        "stream": True,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.get('api_key', '')}",
    }

    attempts = max(1, int(cfg.get("retries", 3)) + 1)
    backoff = max(0.0, float(cfg.get("retry_backoff_sec", 2.0)))
    timeout = int(cfg.get("timeout_sec", 120))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        req = request.Request(
            url=url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        text_parts: list[str] = []
        usage: dict[str, Any] = {}
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(chunk.get("usage"), dict):
                        usage = chunk["usage"]
                    choices = chunk.get("choices", [])
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content", "")
                    if isinstance(content, str) and content:
                        text_parts.append(content)
                    elif isinstance(content, list):
                        for item in content:
                            if not isinstance(item, dict):
                                continue
                            if item.get("type") in {"text", "output_text"}:
                                txt = str(item.get("text", ""))
                                if txt:
                                    text_parts.append(txt)

            text = "".join(text_parts).strip()
            if text:
                return text, usage
            # Empty stream output, fall through to fallback routes.
            raise RuntimeError("OpenAI stream response contained empty content.")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code in {408, 409, 425, 429, 500, 502, 503, 504}
            if retryable and attempt < attempts:
                sleep_sec = backoff * (2 ** (attempt - 1))
                print(
                    f"[WARN] LLM stream retry {attempt}/{attempts - 1} on HTTP {exc.code}.",
                    flush=True,
                )
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
                last_error = RuntimeError(f"HTTP {exc.code} stream calling LLM API: {body[:4000]}")
                continue
            raise RuntimeError(f"HTTP {exc.code} stream calling LLM API: {body[:4000]}") from exc
        except (error.URLError, TimeoutError, RuntimeError) as exc:
            if attempt < attempts:
                sleep_sec = backoff * (2 ** (attempt - 1))
                print(
                    f"[WARN] LLM stream retry {attempt}/{attempts - 1}: {exc}",
                    flush=True,
                )
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
                last_error = exc
                continue
            raise RuntimeError(f"Stream call failed: {exc}") from exc

    if last_error:
        raise RuntimeError(f"Stream call failed after retries: {last_error}") from last_error
    raise RuntimeError("Stream call failed unexpectedly.")


def _call_openai_responses(
    cfg: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, dict[str, Any]]:
    url = _join_api_url(str(cfg.get("base_url", "")), "/responses")
    payload = {
        "model": str(cfg.get("model", "")),
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "temperature": float(cfg.get("temperature", 0.7)),
        "max_output_tokens": int(cfg.get("max_tokens", 2200)),
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.get('api_key', '')}",
    }
    resp = _http_post_json(
        url=url,
        headers=headers,
        payload=payload,
        timeout_sec=int(cfg.get("timeout_sec", 120)),
        retries=int(cfg.get("retries", 3)),
        retry_backoff_sec=float(cfg.get("retry_backoff_sec", 2.0)),
    )
    text = _extract_openai_responses_text(resp)
    if not text.strip():
        raise RuntimeError("OpenAI responses endpoint also returned empty text content.")
    usage = resp.get("usage", {}) if isinstance(resp, dict) else {}
    return text, usage if isinstance(usage, dict) else {}


def _call_anthropic_messages(
    cfg: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, dict[str, Any]]:
    url = _join_api_url(str(cfg.get("base_url", "")), "/messages")
    payload = {
        "model": str(cfg.get("model", "")),
        "max_tokens": int(cfg.get("max_tokens", 2200)),
        "temperature": float(cfg.get("temperature", 0.7)),
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": str(cfg.get("api_key", "")),
        "anthropic-version": "2023-06-01",
    }
    resp = _http_post_json(
        url=url,
        headers=headers,
        payload=payload,
        timeout_sec=int(cfg.get("timeout_sec", 120)),
        retries=int(cfg.get("retries", 3)),
        retry_backoff_sec=float(cfg.get("retry_backoff_sec", 2.0)),
    )
    text = _extract_anthropic_text(resp)
    if not text.strip():
        raise RuntimeError("Claude response contained empty text content.")
    usage = resp.get("usage", {}) if isinstance(resp, dict) else {}
    return text, usage if isinstance(usage, dict) else {}


def _http_post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_sec: int,
    retries: int = 0,
    retry_backoff_sec: float = 0.0,
) -> dict[str, Any]:
    attempts = max(1, retries + 1)
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        req = request.Request(
            url=url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSON response from LLM API: {body[:2000]}") from exc
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            snippet = body[:4000]
            retryable = exc.code in {408, 409, 425, 429, 500, 502, 503, 504}
            if retryable and attempt < attempts:
                sleep_sec = max(0.0, retry_backoff_sec) * (2 ** (attempt - 1))
                print(
                    f"[WARN] LLM HTTP retry {attempt}/{attempts - 1} on status {exc.code}.",
                    flush=True,
                )
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
                last_err = RuntimeError(
                    f"HTTP {exc.code} calling LLM API (retry {attempt}/{attempts - 1}): {snippet}",
                )
                continue
            raise RuntimeError(f"HTTP {exc.code} calling LLM API: {snippet}") from exc
        except (error.URLError, TimeoutError) as exc:
            if attempt < attempts:
                sleep_sec = max(0.0, retry_backoff_sec) * (2 ** (attempt - 1))
                print(
                    f"[WARN] LLM network retry {attempt}/{attempts - 1}: {exc}",
                    flush=True,
                )
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
                last_err = exc
                continue
            if isinstance(exc, error.URLError):
                raise RuntimeError(f"Network error calling LLM API: {exc}") from exc
            raise RuntimeError(f"Timeout calling LLM API: {exc}") from exc

    if last_err:
        raise RuntimeError(f"LLM API call failed after retries: {last_err}") from last_err
    raise RuntimeError("LLM API call failed unexpectedly.")


def _extract_openai_text(resp: dict[str, Any]) -> str:
    if not isinstance(resp, dict):
        return ""
    choices = resp.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text", "")))
        return "\n".join(p for p in parts if p)
    return str(content)


def _extract_openai_responses_text(resp: dict[str, Any]) -> str:
    if not isinstance(resp, dict):
        return ""
    output_text = resp.get("output_text", "")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = resp.get("output", [])
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            ctype = str(c.get("type", ""))
            if ctype in {"output_text", "text"}:
                text = str(c.get("text", "")).strip()
                if text:
                    parts.append(text)
    return "\n".join(parts).strip()


def _extract_anthropic_text(resp: dict[str, Any]) -> str:
    if not isinstance(resp, dict):
        return ""
    content = resp.get("content", [])
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(p for p in parts if p)


def _join_api_url(base_url: str, suffix: str) -> str:
    base = base_url.rstrip("/")
    if not base:
        raise ValueError("base_url cannot be empty for LLM backend.")
    if base.endswith(suffix):
        return base
    return base + suffix


def _render_list(items: list[Any], limit: int) -> str:
    values = [str(x).strip() for x in items if str(x).strip()]
    if not values:
        return "- (none)"
    return "\n".join(f"- {item}" for item in values[:limit])


def _render_dialogue_patterns(items: list[Any], limit: int) -> str:
    lines: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            desc = str(item.get("description", "")).strip()
            if name or desc:
                lines.append(f"- {name}: {desc}".strip())
        else:
            raw = str(item).strip()
            if raw:
                lines.append(f"- {raw}")
    return "\n".join(lines) if lines else "- (none)"


def _render_stage_anchor(template_dna: dict[str, Any], contract: dict[str, Any]) -> str:
    stage_id = str(contract.get("stage_id", "")).strip()
    stage_title = str(contract.get("template_anchor", "")).strip()
    if stage_id or stage_title:
        return f"{stage_id} | {stage_title}".strip(" |")
    stages = template_dna.get("narrative_stages", [])
    if stages:
        stage = stages[0]
        return f"{stage.get('stage_id', '')} | {stage.get('title', '')}".strip(" |")
    return "(unknown)"


def _normalize_principles(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("detail", "")).strip()
        else:
            text = str(item).strip()
        if text:
            result.append(text)
    return result


def _parse_model_output(raw_text: str, contract: dict[str, Any], chapter_no: int) -> tuple[str, str]:
    text = (raw_text or "").strip()
    if not text:
        raise RuntimeError("LLM returned empty response text.")

    chapter_match = _CHAPTER_BLOCK_RE.search(text)
    summary_match = _SUMMARY_BLOCK_RE.search(text)

    chapter_markdown = chapter_match.group(1).strip() if chapter_match else text
    chapter_summary = summary_match.group(1).strip() if summary_match else _auto_summary(contract, chapter_no)
    chapter_markdown = _normalize_draft_markdown(chapter_markdown, contract, chapter_no)
    chapter_summary = chapter_summary or _auto_summary(contract, chapter_no)
    return chapter_markdown, chapter_summary


def _normalize_draft_markdown(chapter_markdown: str, contract: dict[str, Any], chapter_no: int) -> str:
    title = str(contract.get("chapter_title", f"Chapter {chapter_no}")).strip()
    text = chapter_markdown.strip()
    if not text.startswith("#"):
        text = f"# {title}\n\n{text}"
    if "## 正文" not in text:
        lines = text.splitlines()
        if lines and lines[0].startswith("#"):
            body = "\n".join(lines[1:]).strip()
            text = f"{lines[0]}\n\n## 正文\n{body}\n"
        else:
            text = f"# {title}\n\n## 正文\n{text}\n"
    if "## 本章模板对齐点" not in text:
        text = text.rstrip() + "\n\n" + _render_alignment_section(contract) + "\n"
    text = text.replace("TODO", "").replace("TBD", "").replace("[TODO]", "").replace("......", "")
    return text.rstrip() + "\n"


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


def _auto_summary(contract: dict[str, Any], chapter_no: int) -> str:
    objective = str(contract.get("chapter_objective", "")).strip()
    escalation = str(contract.get("escalation_target", "")).strip()
    if objective and escalation:
        return f"第{chapter_no}章完成“{objective}”推进，并抛出“{escalation}”作为下一章压力。"
    if objective:
        return f"第{chapter_no}章围绕“{objective}”完成关键推进。"
    return f"第{chapter_no}章完成阶段内关键推进并提升冲突压力。"

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model_writer import generate_text_with_llm, normalize_writer_config
from .remix_bundle import validate_remix_bundle


_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_SYSTEM_PROMPT = (
    "You are executing a project-owned writing skill. "
    "Strictly follow the provided contract exactly and return only one valid JSON object."
)
_EXECUTION_INSTRUCTION = (
    "Strictly follow the SKILL.md below. "
    "The final output must be only one valid JSON object with no markdown wrapper and no extra commentary."
)
_JSON_REPAIR_SYSTEM_PROMPT = (
    "You repair malformed JSON. "
    "Return only one valid JSON object. "
    "Do not add markdown, comments, explanations, or extra fields. "
    "Preserve the original meaning and content as much as possible."
)


def list_skill_names() -> list[str]:
    return sorted(
        path.name
        for path in _SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    )


def resolve_skill_path(skill_name: str) -> Path:
    path = _SKILLS_DIR / skill_name / "SKILL.md"
    if path.exists():
        return path
    available = ", ".join(list_skill_names()) or "<none>"
    raise ValueError(f"Unknown skill '{skill_name}'. Available skills: {available}")


def get_skill_text(skill_name: str) -> str:
    return resolve_skill_path(skill_name).read_text(encoding="utf-8")


def export_skill(skill_name: str, out_path: Path) -> Path:
    text = get_skill_text(skill_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return out_path


def build_skill_prompt(
    *,
    skill_name: str,
    viral_story_path: Path,
    new_story_idea_path: Path,
) -> tuple[str, str]:
    skill_text = get_skill_text(skill_name)
    viral_story = _read_required_text(viral_story_path)
    new_story_idea = _read_required_text(new_story_idea_path)
    user_prompt = (
        "# Skill Execution Package\n\n"
        f"## Skill Name\n{skill_name}\n\n"
        f"## Execution Instruction\n{_EXECUTION_INSTRUCTION}\n\n"
        f"## SKILL.md\n{skill_text.rstrip()}\n\n"
        f"## Input: viral_story\n{viral_story.rstrip()}\n\n"
        f"## Input: new_story_idea\n{new_story_idea.rstrip()}\n"
    )
    return _SYSTEM_PROMPT, user_prompt


def execute_skill_scaffold(
    *,
    skill_name: str,
    viral_story_path: Path,
    new_story_idea_path: Path,
    out_path: Path,
    writer_config: dict[str, Any],
) -> Path:
    cfg = normalize_writer_config(writer_config)
    if cfg.get("backend") == "builtin":
        raise ValueError("skill scaffold requires openai/claude writer config; builtin is not supported")

    system_prompt, user_prompt = build_skill_prompt(
        skill_name=skill_name,
        viral_story_path=viral_story_path,
        new_story_idea_path=new_story_idea_path,
    )
    raw_text, _meta = generate_text_with_llm(
        writer_config=cfg,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    try:
        payload = _validate_bundle_json(raw_text)
    except ValueError:
        repaired_text, _repair_meta = generate_text_with_llm(
            writer_config=cfg,
            system_prompt=_JSON_REPAIR_SYSTEM_PROMPT,
            user_prompt=(
                "Repair the following content into one valid JSON object only. "
                "Do not summarize or change semantics unless required to fix JSON syntax.\n\n"
                f"{raw_text}"
            ),
        )
        raw_path = out_path.with_suffix(".raw.json")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(repaired_text, encoding="utf-8")
        payload = _validate_bundle_json(repaired_text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _validate_bundle_json(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM output is not a valid remix bundle JSON") from exc
    try:
        return validate_remix_bundle(payload)
    except Exception as exc:
        raise ValueError("LLM output is not a valid remix bundle JSON") from exc


def _read_required_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Input file is empty: {path}")
    return text

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


REMIX_BUNDLE_SCHEMA_VERSION = "remix_bundle.v1"
_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def resolve_default_remix_bundle_path(project_root: Path) -> Path:
    return _resolve_first_existing(
        project_root / "remix_bundle.json",
        project_root / "inputs" / "remix_bundle.json",
        project_root / "remix_bundle.md",
        project_root / "inputs" / "remix_bundle.md",
    )


def load_remix_bundle(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Remix bundle not found: {path}")
    raw = path.read_text(encoding="utf-8")
    payload = _parse_bundle_document(raw, path)
    return validate_remix_bundle(payload)


def validate_remix_bundle(payload: Any) -> dict[str, Any]:
    bundle = _expect_dict(payload, "remix_bundle")
    schema_version = str(bundle.get("schema_version", "")).strip()
    if schema_version != REMIX_BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"remix_bundle.schema_version must be '{REMIX_BUNDLE_SCHEMA_VERSION}', got '{schema_version or '<empty>'}'",
        )

    project_brief = _expect_dict(bundle.get("project_brief"), "project_brief")
    _expect_nonempty_str(project_brief.get("title"), "project_brief.title")
    _expect_positive_int(project_brief.get("episode_count"), "project_brief.episode_count")
    _expect_str_list(project_brief.get("must_keep"), "project_brief.must_keep")

    source_trace = _expect_dict(bundle.get("source_trace"), "source_trace")
    _expect_nonempty_str(source_trace.get("viral_story_title"), "source_trace.viral_story_title")
    _expect_nonempty_str(source_trace.get("new_story_title"), "source_trace.new_story_title")

    template_dna = _expect_dict(bundle.get("template_dna"), "template_dna")
    _expect_nonempty_str(template_dna.get("core_premise"), "template_dna.core_premise")
    _expect_list(template_dna.get("template_formulas", []), "template_dna.template_formulas")
    _expect_list(template_dna.get("dialogue_patterns", []), "template_dna.dialogue_patterns")
    _expect_list(template_dna.get("principles", []), "template_dna.principles")
    _expect_list(template_dna.get("reusable_motifs", []), "template_dna.reusable_motifs")
    narrative_stages = _expect_list(template_dna.get("narrative_stages", []), "template_dna.narrative_stages")
    rhythm_beats = _expect_list(template_dna.get("rhythm_beats", []), "template_dna.rhythm_beats")
    if not narrative_stages and not rhythm_beats:
        raise ValueError("template_dna must include narrative_stages or rhythm_beats")

    story_bible = _expect_dict(bundle.get("story_bible"), "story_bible")
    metadata = _expect_dict(story_bible.get("metadata"), "story_bible.metadata")
    story_title = _expect_nonempty_str(metadata.get("title"), "story_bible.metadata.title")
    target_chapters = _expect_positive_int(metadata.get("target_chapters"), "story_bible.metadata.target_chapters")
    _expect_positive_int(metadata.get("chapter_word_target"), "story_bible.metadata.chapter_word_target")
    _expect_dict(story_bible.get("premise"), "story_bible.premise")
    _expect_dict(story_bible.get("world"), "story_bible.world")
    characters = _expect_list(story_bible.get("characters", []), "story_bible.characters")
    if not characters:
        raise ValueError("story_bible.characters must contain at least one character")
    _expect_dict(story_bible.get("conflicts"), "story_bible.conflicts")
    _expect_dict(story_bible.get("constraints"), "story_bible.constraints")

    structure_map = _expect_dict(bundle.get("structure_map"), "structure_map")
    book_title = _expect_nonempty_str(structure_map.get("book_title"), "structure_map.book_title")
    map_target = _expect_positive_int(structure_map.get("target_chapters"), "structure_map.target_chapters")
    if book_title != story_title:
        raise ValueError("structure_map.book_title must match story_bible.metadata.title")
    if map_target != target_chapters:
        raise ValueError("structure_map.target_chapters must match story_bible.metadata.target_chapters")

    stage_contracts = _expect_list(structure_map.get("stage_contracts"), "structure_map.stage_contracts")
    if not stage_contracts:
        raise ValueError("structure_map.stage_contracts must contain at least one stage")
    for idx, stage in enumerate(stage_contracts, start=1):
        stage_obj = _expect_dict(stage, f"structure_map.stage_contracts[{idx}]")
        stage_obj["stage_id"] = _coerce_nonempty_str(stage_obj.get("stage_id"), f"structure_map.stage_contracts[{idx}].stage_id")
        _expect_nonempty_str(stage_obj.get("template_title"), f"structure_map.stage_contracts[{idx}].template_title")
        _expect_positive_int(stage_obj.get("chapter_start"), f"structure_map.stage_contracts[{idx}].chapter_start")
        _expect_positive_int(stage_obj.get("chapter_end"), f"structure_map.stage_contracts[{idx}].chapter_end")
        _expect_nonempty_str(stage_obj.get("story_goal"), f"structure_map.stage_contracts[{idx}].story_goal")
        _expect_str_list(stage_obj.get("must_keep"), f"structure_map.stage_contracts[{idx}].must_keep")
        _expect_nonempty_str(
            stage_obj.get("escalation_target"),
            f"structure_map.stage_contracts[{idx}].escalation_target",
        )

    chapter_plan = _expect_list(structure_map.get("chapter_plan"), "structure_map.chapter_plan")
    if not chapter_plan:
        raise ValueError("structure_map.chapter_plan must contain at least one chapter")
    for idx, chapter in enumerate(chapter_plan, start=1):
        chapter_obj = _expect_dict(chapter, f"structure_map.chapter_plan[{idx}]")
        _expect_positive_int(chapter_obj.get("chapter"), f"structure_map.chapter_plan[{idx}].chapter")
        _expect_nonempty_str(chapter_obj.get("title"), f"structure_map.chapter_plan[{idx}].title")
        chapter_obj["stage_id"] = _coerce_nonempty_str(chapter_obj.get("stage_id"), f"structure_map.chapter_plan[{idx}].stage_id")
        _expect_nonempty_str(chapter_obj.get("objective"), f"structure_map.chapter_plan[{idx}].objective")

    human_readable = bundle.get("human_readable_markdown", "")
    if human_readable is None:
        bundle["human_readable_markdown"] = ""
    elif not isinstance(human_readable, str):
        raise ValueError("human_readable_markdown must be a string")
    else:
        bundle["human_readable_markdown"] = human_readable
    return bundle


def _parse_bundle_document(raw: str, path: Path) -> dict[str, Any]:
    text = raw.lstrip("\ufeff").strip()
    if not text:
        raise ValueError(f"Remix bundle is empty: {path}")

    if text.startswith("{"):
        return _decode_json(text, path)

    for match in _JSON_BLOCK_RE.finditer(text):
        candidate = match.group(1).strip()
        try:
            data = _decode_json(candidate, path)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("schema_version") == REMIX_BUNDLE_SCHEMA_VERSION:
            return data

    raise ValueError(f"Could not find a valid remix bundle JSON block in {path}")


def _decode_json(raw: str, path: Path) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid remix bundle JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Remix bundle payload must be a JSON object: {path}")
    return data


def _resolve_first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _expect_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _expect_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return value


def _expect_str_list(value: Any, field_name: str) -> list[str]:
    items = _expect_list(value, field_name)
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{idx}] must be a non-empty string")
    return [str(item).strip() for item in items]


def _expect_nonempty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _coerce_nonempty_str(value: Any, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        text = str(value).strip()
        if text:
            return text
    raise ValueError(f"{field_name} must be a non-empty string")


def _expect_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    if isinstance(value, int):
        number = value
    else:
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return number

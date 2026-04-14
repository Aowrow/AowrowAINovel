from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .app_config import DEFAULT_RUNTIME_CONFIG
from .asset_indexer import read_manifest, update_manifest
from .character_profile import build_initial_character_profiles
from .relationship_graph import build_relationship_graph
from .storage_layout import BookLayoutPaths, chapter_dir, ensure_book_layout, outline_file


CHAPTER_FILE_RE = re.compile(r"^第(\d+)章\.txt$")


class AssetStore:
    def __init__(self, book_root: Path) -> None:
        self.layout: BookLayoutPaths = ensure_book_layout(book_root)
        self.storage_cfg = _resolve_storage_config(self.layout.book_root)

    def init_project_assets(
        self,
        template_dna: dict[str, Any],
        story_bible: dict[str, Any],
        structure_map: dict[str, Any],
    ) -> None:
        metadata = story_bible.get("metadata", {}) if isinstance(story_bible, dict) else {}
        title = str(metadata.get("title", "")).strip() or "Untitled Story"
        self._write_json(self.layout.project_template_dna, template_dna)
        self._write_json(self.layout.project_story_bible, story_bible)
        self._write_json(self.layout.project_structure_map, structure_map)
        self._write_json(
            self.layout.project_metadata,
            {
                "title": title,
                "genre": str(metadata.get("genre", "")),
                "theme": str(metadata.get("theme", "")),
                "tone": str(metadata.get("tone", "")),
                "chapter_word_target": metadata.get("chapter_word_target"),
            },
        )
        world = story_bible.get("world", {}) if isinstance(story_bible, dict) else {}
        self._write_json(
            self.layout.world_rules,
            {
                "era": world.get("era", ""),
                "locations": world.get("locations", []),
                "power_system": world.get("power_system", ""),
                "rules": world.get("rules", []),
            },
        )
        self._write_json(self.layout.world_conflicts, story_bible.get("conflicts", {}))
        profiles = build_initial_character_profiles(story_bible)
        char_index: list[dict[str, Any]] = []
        for payload in profiles:
            cid = str(payload.get("id", "")).strip()
            if not cid:
                continue
            self._write_json(self.layout.characters_dir / f"{cid}.json", payload)
            char_index.append({"id": cid, "name": payload["name"], "role": payload["role"]})
        self._write_json(self.layout.characters_index, {"characters": char_index})
        self._write_json(self.layout.relationships_graph, build_relationship_graph(profiles))

        chapter_plan = structure_map.get("chapter_plan", []) if isinstance(structure_map, dict) else []
        for item in chapter_plan:
            chapter_no = _safe_int(item.get("chapter"), 0)
            if chapter_no <= 0:
                continue
            self._write_json(outline_file(self.layout.outlines_dir, chapter_no), item)

        self._write_json(self.layout.foreshadow_ledger, {"foreshadows": []})
        self.refresh_manifest(story_bible=story_bible)

    def write_runtime(self, runtime_state: dict[str, Any]) -> None:
        self._write_json(self.layout.runtime_state, runtime_state)
        ledger = runtime_state.get("foreshadow_ledger", []) if isinstance(runtime_state, dict) else []
        foreshadows = runtime_state.get("foreshadows", []) if isinstance(runtime_state, dict) else []
        self._write_json(
            self.layout.foreshadow_ledger,
            {"foreshadows": foreshadows, "foreshadow_ledger": ledger},
        )

    def write_t5_summary(self, summary: dict[str, Any]) -> None:
        self._write_json(self.layout.t5_summary, summary)

    def write_chapter_package(
        self,
        package: dict[str, Any],
        storage_cfg: dict[str, Any] | None = None,
    ) -> int:
        cfg = _merge_storage_config(self.storage_cfg, storage_cfg)
        chapter_no = _safe_int(package.get("chapter"), 0)
        if chapter_no <= 0:
            raise ValueError("Invalid chapter number in package.")
        ch_dir = chapter_dir(self.layout.chapters_dir, chapter_no)
        ch_dir.mkdir(parents=True, exist_ok=True)

        draft = str(package.get("draft_markdown", "") or "")
        summary_text = str(package.get("chapter_summary", "") or "")
        self._write_text(ch_dir / "draft.md", draft)
        self._write_json(ch_dir / "summary.json", {"chapter": chapter_no, "summary": summary_text})
        self._write_json(ch_dir / "context.json", package.get("context_bundle", {}))
        self._write_json(ch_dir / "contract.json", package.get("contract", {}))
        self._write_json(ch_dir / "analysis.json", package.get("chapter_analysis", {}))
        self._write_json(ch_dir / "audit.json", package.get("t7_audit_report", {}))
        self._write_json(ch_dir / "state_delta.json", package.get("state_delta", {}))
        diff_report = str(package.get("t7_diff_report_md", "") or "").strip()
        if diff_report:
            self._write_text(ch_dir / "diff.md", diff_report)
        else:
            self._remove_file(ch_dir / "diff.md")
        if bool(cfg.get("write_alignment_file", False)):
            self._write_json(ch_dir / "alignment.json", package.get("alignment_report", {}))
        else:
            self._remove_file(ch_dir / "alignment.json")
        if bool(cfg.get("write_debug_package", False)):
            self._write_json(ch_dir / "package.json", package)
        else:
            self._remove_file(ch_dir / "package.json")

        if bool(cfg.get("export_plain_text", False)) or bool(cfg.get("export_full_book", False)):
            self._export_chapter_text(
                chapter_no=chapter_no,
                draft_md=draft,
                export_plain_text=bool(cfg.get("export_plain_text", False)),
                export_full_book=bool(cfg.get("export_full_book", False)),
            )
        else:
            self._remove_export_artifacts(chapter_no)
        self.write_quality_history(chapter_no, package.get("t7_audit_report", {}))
        return chapter_no

    def write_quality_history(self, chapter_no: int, audit_report: dict[str, Any]) -> None:
        current = {"chapters": []}
        path = self.layout.runtime_quality_history
        if path.exists():
            loaded = _read_json_object_or_default(path, default={"chapters": []})
            if isinstance(loaded, dict):
                current = loaded

        failures = _quality_failures(audit_report)
        entry = {
            "chapter": chapter_no,
            "pass": bool(audit_report.get("pass", False)),
            "hard_failures": sum(1 for item in failures if str(item.get("severity", "")).lower() == "error"),
            "warnings": sum(1 for item in failures if str(item.get("severity", "")).lower() == "warning"),
        }

        chapters = current.setdefault("chapters", [])
        if not isinstance(chapters, list):
            chapters = []
            current["chapters"] = chapters
        chapters[:] = [item for item in chapters if _safe_int(item.get("chapter"), -1) != chapter_no]
        chapters.append(entry)
        chapters.sort(key=lambda item: _safe_int(item.get("chapter"), 0))
        self._write_json(path, current)

    def existing_exported_chapters(self) -> list[int]:
        numbers: set[int] = set()
        if self.layout.chapters_dir.exists():
            for p in self.layout.chapters_dir.iterdir():
                if not p.is_dir():
                    continue
                try:
                    numbers.add(int(p.name))
                except ValueError:
                    continue
        if not self.layout.exports_dir.exists():
            return sorted(numbers)
        for p in self.layout.exports_dir.glob("*.txt"):
            m = CHAPTER_FILE_RE.match(p.name)
            if not m:
                continue
            try:
                numbers.add(int(m.group(1)))
            except ValueError:
                continue
        return sorted(numbers)

    def refresh_manifest(
        self,
        story_bible: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = read_manifest(self.layout.manifest)
        title = ""
        if isinstance(story_bible, dict):
            title = str(story_bible.get("metadata", {}).get("title", "")).strip()
        if not title:
            title = str(existing.get("book_title", "")).strip() or "Untitled Story"
        chapters = self._discover_chapter_dirs()
        return update_manifest(self.layout, title=title, chapter_numbers=chapters, extra=extra)

    def _discover_chapter_dirs(self) -> list[int]:
        numbers: list[int] = []
        if not self.layout.chapters_dir.exists():
            return numbers
        for p in self.layout.chapters_dir.iterdir():
            if not p.is_dir():
                continue
            try:
                numbers.append(int(p.name))
            except ValueError:
                continue
        numbers.sort()
        return numbers

    def _export_chapter_text(
        self,
        chapter_no: int,
        draft_md: str,
        export_plain_text: bool,
        export_full_book: bool,
    ) -> None:
        self.layout.exports_dir.mkdir(parents=True, exist_ok=True)
        readable_md = _strip_alignment_section(draft_md)
        readable_txt = _markdown_to_plain_text(readable_md).strip() or readable_md.strip()
        chapter_title = f"第{chapter_no}章"
        chapter_out = self.layout.exports_dir / f"{chapter_title}.txt"
        chapter_body = f"{chapter_title}\n\n{readable_txt.strip()}\n"
        if export_plain_text:
            self._write_text(chapter_out, chapter_body)
        else:
            self._remove_file(chapter_out)

        section = chapter_body.strip()
        full_book_path = self.layout.full_book_export
        if not export_full_book:
            return
        if full_book_path.exists():
            existing = full_book_path.read_text(encoding="utf-8-sig").strip()
            self._write_text(full_book_path, _append_full_book_text(existing, section))
        else:
            self._write_text(full_book_path, f"{section}\n" if section else "")

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _remove_export_artifacts(self, chapter_no: int) -> None:
        chapter_title = f"第{chapter_no}章"
        self._remove_file(self.layout.exports_dir / f"{chapter_title}.txt")

    def _remove_file(self, path: Path) -> None:
        if path.exists():
            path.unlink()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_storage_config(book_root: Path) -> dict[str, Any]:
    defaults = deepcopy(DEFAULT_RUNTIME_CONFIG.get("storage", {}))
    conf_path = _find_runtime_config(book_root)
    if conf_path is None:
        return defaults
    loaded = _read_json_object(conf_path)
    configured = loaded.get("storage", {}) if isinstance(loaded, dict) else {}
    return _merge_storage_config(defaults, configured)


def _find_runtime_config(book_root: Path) -> Path | None:
    resolved = book_root.resolve()
    for candidate_dir in (resolved, *resolved.parents):
        candidate = candidate_dir / "template_novel_engine.config.json"
        if candidate.exists():
            return candidate
    return None


def _read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Config JSON must be an object: {path}")
    return data


def _read_json_object_or_default(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return deepcopy(default)
    if not isinstance(data, dict):
        return deepcopy(default)
    return data


def _merge_storage_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if isinstance(override, dict):
        merged.update(override)
    return merged


def _quality_failures(audit_report: dict[str, Any]) -> list[dict[str, Any]]:
    after = audit_report.get("after", {}) if isinstance(audit_report, dict) else {}
    failures = after.get("failures") if isinstance(after, dict) else None
    if isinstance(failures, list):
        return [item for item in failures if isinstance(item, dict)]
    direct = audit_report.get("failures") if isinstance(audit_report, dict) else None
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)]
    return []


def _strip_alignment_section(draft_markdown: str) -> str:
    lines = draft_markdown.splitlines()
    out: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## 本章模板对齐点") or stripped.startswith("## Template Alignment"):
            skip = True
            continue
        if skip and stripped.startswith("## "):
            skip = False
        if not skip:
            out.append(line)
    return "\n".join(out).strip()


def _markdown_to_plain_text(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"^#{1,6}\s*", "", line).rstrip()
        cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned)
        cleaned = re.sub(r"`+", "", cleaned)
        if cleaned.startswith(">"):
            cleaned = cleaned.lstrip(">").strip()
        out.append(cleaned)
    return "\n".join(out).strip()


def _append_full_book_text(existing_text: str, appended_text: str) -> str:
    existing = existing_text.strip()
    appended = appended_text.strip()
    if not existing:
        return f"{appended}\n" if appended else ""
    if not appended:
        return f"{existing}\n"

    chapter_match = re.match(r"^(第\d+章)", appended)
    if chapter_match:
        chapter_heading = chapter_match.group(1)
        sections = [section.strip() for section in re.split(r"\n\n={40}\n\n", existing) if section.strip()]
        replaced = False
        for idx, section in enumerate(sections):
            if section.startswith(chapter_heading):
                sections[idx] = appended
                replaced = True
                break
        if not replaced:
            sections.append(appended)
        return (f"\n\n{'=' * 40}\n\n").join(sections) + "\n"

    sep = f"\n\n{'=' * 40}\n\n"
    return f"{existing}{sep}{appended}\n"

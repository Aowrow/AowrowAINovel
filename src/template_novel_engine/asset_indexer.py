from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .storage_layout import LAYOUT_VERSION, BookLayoutPaths


def update_manifest(
    layout: BookLayoutPaths,
    title: str,
    chapter_numbers: list[int],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
        "layout_version": LAYOUT_VERSION,
        "book_title": title,
        "chapter_count": len(chapter_numbers),
        "chapters": sorted(chapter_numbers),
        "paths": {
            "project": _rel(layout.book_root, layout.project_dir),
            "world": _rel(layout.book_root, layout.world_dir),
            "characters": _rel(layout.book_root, layout.characters_dir),
            "relationships": _rel(layout.book_root, layout.relationships_dir),
            "outlines": _rel(layout.book_root, layout.outlines_dir),
            "foreshadows": _rel(layout.book_root, layout.foreshadows_dir),
            "chapters": _rel(layout.book_root, layout.chapters_dir),
            "runtime_state": _rel(layout.book_root, layout.runtime_state),
            "exports": _rel(layout.book_root, layout.exports_dir),
            "full_book": _rel(layout.book_root, layout.full_book_export),
            "t5_summary": _rel(layout.book_root, layout.t5_summary),
        },
    }
    if isinstance(extra, dict) and extra:
        manifest["extra"] = extra
    layout.manifest.parent.mkdir(parents=True, exist_ok=True)
    layout.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except Exception:
        return str(p.resolve())


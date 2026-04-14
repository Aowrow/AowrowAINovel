from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


LAYOUT_VERSION = "v2"


@dataclass(frozen=True)
class BookLayoutPaths:
    book_root: Path
    project_dir: Path
    world_dir: Path
    characters_dir: Path
    relationships_dir: Path
    outlines_dir: Path
    foreshadows_dir: Path
    chapters_dir: Path
    runtime_dir: Path
    index_dir: Path
    exports_dir: Path
    project_metadata: Path
    project_template_dna: Path
    project_story_bible: Path
    project_structure_map: Path
    world_rules: Path
    world_conflicts: Path
    characters_index: Path
    relationships_graph: Path
    foreshadow_ledger: Path
    runtime_state: Path
    runtime_quality_history: Path
    manifest: Path
    t5_summary: Path
    full_book_export: Path


def resolve_book_layout(book_root: Path) -> BookLayoutPaths:
    root = book_root.resolve()
    project_dir = root / "project"
    world_dir = root / "world"
    characters_dir = root / "characters"
    relationships_dir = root / "relationships"
    outlines_dir = root / "outlines"
    foreshadows_dir = root / "foreshadows"
    chapters_dir = root / "chapters"
    runtime_dir = root / "runtime"
    index_dir = root / "index"
    exports_dir = root / "exports"
    return BookLayoutPaths(
        book_root=root,
        project_dir=project_dir,
        world_dir=world_dir,
        characters_dir=characters_dir,
        relationships_dir=relationships_dir,
        outlines_dir=outlines_dir,
        foreshadows_dir=foreshadows_dir,
        chapters_dir=chapters_dir,
        runtime_dir=runtime_dir,
        index_dir=index_dir,
        exports_dir=exports_dir,
        project_metadata=project_dir / "metadata.json",
        project_template_dna=project_dir / "template_dna.json",
        project_story_bible=project_dir / "story_bible.json",
        project_structure_map=project_dir / "structure_map.json",
        world_rules=world_dir / "world_rules.json",
        world_conflicts=world_dir / "conflicts.json",
        characters_index=characters_dir / "index.json",
        relationships_graph=relationships_dir / "graph.json",
        foreshadow_ledger=foreshadows_dir / "ledger.json",
        runtime_state=runtime_dir / "state.json",
        runtime_quality_history=runtime_dir / "quality_history.json",
        manifest=index_dir / "manifest.json",
        t5_summary=index_dir / "t5_summary.json",
        full_book_export=exports_dir / "全书.txt",
    )


def ensure_book_layout(book_root: Path) -> BookLayoutPaths:
    paths = resolve_book_layout(book_root)
    for directory in (
        paths.project_dir,
        paths.world_dir,
        paths.characters_dir,
        paths.relationships_dir,
        paths.outlines_dir,
        paths.foreshadows_dir,
        paths.chapters_dir,
        paths.runtime_dir,
        paths.index_dir,
        paths.exports_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def chapter_dir(chapters_root: Path, chapter_no: int) -> Path:
    return chapters_root / f"{int(chapter_no):04d}"


def outline_file(outlines_root: Path, chapter_no: int) -> Path:
    return outlines_root / f"chapter_{int(chapter_no):04d}.json"


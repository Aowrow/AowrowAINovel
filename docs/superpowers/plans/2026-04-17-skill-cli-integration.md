# Skill CLI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a built-in `viral-story-remix` skill to `AowrowAINovel` and expose it through CLI commands for listing, showing, exporting, and scaffolding model-ready prompt packages.

**Architecture:** Vendor the skill as a project asset under `src/template_novel_engine/skills`, add one small `skill_assets.py` helper module for asset lookup and scaffold generation, and wire a new `skill` command group into the existing `cli.py`. Keep the current `generate` and `remix_bundle` flow unchanged so the new feature is additive rather than invasive.

**Tech Stack:** Python 3, argparse, pathlib, unittest

---

## File Map

- Create: `src/template_novel_engine/skills/viral-story-remix/SKILL.md`
  Purpose: vendored in-project source of truth for the skill text.
- Create: `src/template_novel_engine/skill_assets.py`
  Purpose: list, resolve, read, export, and scaffold built-in skills.
- Create: `tests/test_skill_assets.py`
  Purpose: unit tests for the new skill asset helpers and parser wiring.
- Modify: `src/template_novel_engine/cli.py`
  Purpose: add `skill` subcommands and call the helper module.
- Modify: `README.md`
  Purpose: document the built-in skill workflow.

### Task 1: Add failing tests for the skill asset layer

**Files:**
- Create: `tests/test_skill_assets.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Write the failing test file**

```python
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from template_novel_engine.skill_assets import (
    build_skill_scaffold,
    export_skill,
    get_skill_text,
    list_skill_names,
)


class SkillAssetsTests(unittest.TestCase):
    def test_list_skill_names_includes_viral_story_remix(self) -> None:
        self.assertIn("viral-story-remix", list_skill_names())

    def test_get_skill_text_returns_vendored_skill_content(self) -> None:
        text = get_skill_text("viral-story-remix")

        self.assertIn("name: viral-story-remix", text)
        self.assertIn("## Output Contract", text)

    def test_export_skill_writes_exact_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "viral-story-remix.SKILL.md"

            export_skill("viral-story-remix", out_path)

            self.assertEqual(out_path.read_text(encoding="utf-8"), get_skill_text("viral-story-remix"))

    def test_build_skill_scaffold_writes_expected_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            viral_story_path = root / "viral_story.md"
            new_story_idea_path = root / "new_story_idea.md"
            out_path = root / "skill_package.md"
            viral_story_path.write_text("爆款故事原文", encoding="utf-8")
            new_story_idea_path.write_text("新故事思路", encoding="utf-8")

            result = build_skill_scaffold(
                skill_name="viral-story-remix",
                viral_story_path=viral_story_path,
                new_story_idea_path=new_story_idea_path,
                out_path=out_path,
            )

            content = out_path.read_text(encoding="utf-8")
            self.assertEqual(result, out_path)
            self.assertIn("# Skill Execution Package", content)
            self.assertIn("## Skill Name\nviral-story-remix", content)
            self.assertIn("## SKILL.md", content)
            self.assertIn("## Input: viral_story\n爆款故事原文", content)
            self.assertIn("## Input: new_story_idea\n新故事思路", content)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new test file and verify it fails**

Run: `python -m unittest tests.test_skill_assets -v`

Expected: FAIL with `ModuleNotFoundError` for `template_novel_engine.skill_assets`.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_skill_assets.py
git commit -m "test: add skill asset contract coverage"
```

### Task 2: Implement the minimal skill asset module and vendor the skill

**Files:**
- Create: `src/template_novel_engine/skills/viral-story-remix/SKILL.md`
- Create: `src/template_novel_engine/skill_assets.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Copy the draft skill into the package assets**

Create `src/template_novel_engine/skills/viral-story-remix/SKILL.md` with the exact content from `D:\codexright\skill-drafts\viral-story-remix\SKILL.md`.

- [ ] **Step 2: Write the minimal implementation module**

```python
from __future__ import annotations

from pathlib import Path


_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_SCAFFOLD_INSTRUCTION = (
    "Strictly follow the SKILL.md below. The final output must contain only:\n"
    "1. `## Remix Bundle JSON`\n"
    "2. `## Companion Markdown`"
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


def build_skill_scaffold(
    *,
    skill_name: str,
    viral_story_path: Path,
    new_story_idea_path: Path,
    out_path: Path,
) -> Path:
    skill_text = get_skill_text(skill_name)
    viral_story = _read_required_text(viral_story_path)
    new_story_idea = _read_required_text(new_story_idea_path)
    content = (
        "# Skill Execution Package\n\n"
        f"## Skill Name\n{skill_name}\n\n"
        f"## Execution Instruction\n{_SCAFFOLD_INSTRUCTION}\n\n"
        f"## SKILL.md\n{skill_text.rstrip()}\n\n"
        f"## Input: viral_story\n{viral_story.rstrip()}\n\n"
        f"## Input: new_story_idea\n{new_story_idea.rstrip()}\n"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path


def _read_required_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Input file is empty: {path}")
    return text
```

- [ ] **Step 3: Run the new test file and verify it passes**

Run: `python -m unittest tests.test_skill_assets -v`

Expected: PASS for all four tests.

- [ ] **Step 4: Commit the implementation**

```bash
git add src/template_novel_engine/skills/viral-story-remix/SKILL.md src/template_novel_engine/skill_assets.py tests/test_skill_assets.py
git commit -m "feat: add built-in viral story remix skill assets"
```

### Task 3: Add failing CLI parser coverage for the new `skill` commands

**Files:**
- Modify: `tests/test_skill_assets.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Extend the test file with parser assertions**

Add imports and test methods:

```python
from template_novel_engine.app_config import load_runtime_config
from template_novel_engine.cli import _build_parser
```

```python
    def test_parser_accepts_skill_subcommands(self) -> None:
        runtime_cfg = load_runtime_config(PROJECT_ROOT)
        parser = _build_parser(PROJECT_ROOT, runtime_cfg)

        args = parser.parse_args(["skill", "show", "viral-story-remix"])

        self.assertEqual(args.command, "skill")
        self.assertEqual(args.skill_command, "show")
        self.assertEqual(args.name, "viral-story-remix")

    def test_parser_accepts_skill_scaffold_arguments(self) -> None:
        runtime_cfg = load_runtime_config(PROJECT_ROOT)
        parser = _build_parser(PROJECT_ROOT, runtime_cfg)

        args = parser.parse_args(
            [
                "skill",
                "scaffold",
                "viral-story-remix",
                "--viral-story",
                "viral_story.md",
                "--new-story-idea",
                "new_story_idea.md",
                "--out",
                "package.md",
            ]
        )

        self.assertEqual(args.command, "skill")
        self.assertEqual(args.skill_command, "scaffold")
        self.assertEqual(args.name, "viral-story-remix")
        self.assertEqual(args.viral_story, "viral_story.md")
        self.assertEqual(args.new_story_idea, "new_story_idea.md")
        self.assertEqual(args.out, "package.md")
```

- [ ] **Step 2: Run the parser-focused tests and verify they fail**

Run: `python -m unittest tests.test_skill_assets.SkillAssetsTests.test_parser_accepts_skill_subcommands tests.test_skill_assets.SkillAssetsTests.test_parser_accepts_skill_scaffold_arguments -v`

Expected: FAIL because `skill` is not yet a recognized command.

- [ ] **Step 3: Commit the failing parser tests**

```bash
git add tests/test_skill_assets.py
git commit -m "test: cover skill cli parser"
```

### Task 4: Wire `skill` into the CLI with minimal command handlers

**Files:**
- Modify: `src/template_novel_engine/cli.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Add the helper imports near the top of `cli.py`**

```python
from .skill_assets import build_skill_scaffold, export_skill, get_skill_text, list_skill_names
```

- [ ] **Step 2: Add command dispatch in `main()`**

Insert a new branch before the `run-all` branch:

```python
        if args.command == "skill":
            _run_skill_command(args)
            return 0
```

- [ ] **Step 3: Add the parser branch in `_build_parser()`**

Insert this block before `run-all`:

```python
    skill_cmd = sub.add_parser("skill", help="Work with built-in project skills.")
    skill_sub = skill_cmd.add_subparsers(dest="skill_command")

    skill_list = skill_sub.add_parser("list", help="List built-in skills.")

    skill_show = skill_sub.add_parser("show", help="Print a built-in skill.")
    skill_show.add_argument("name", help="Built-in skill name.")

    skill_export = skill_sub.add_parser("export", help="Export a built-in skill to a file.")
    skill_export.add_argument("name", help="Built-in skill name.")
    skill_export.add_argument("--out", required=True, help="Output file path.")

    skill_scaffold = skill_sub.add_parser("scaffold", help="Build a model-ready execution package.")
    skill_scaffold.add_argument("name", help="Built-in skill name.")
    skill_scaffold.add_argument("--viral-story", required=True, help="Input viral story path.")
    skill_scaffold.add_argument("--new-story-idea", required=True, help="Input new story idea path.")
    skill_scaffold.add_argument("--out", required=True, help="Output markdown package path.")
```

- [ ] **Step 4: Add the new command handler functions near the utility helpers**

```python
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
        out_path = build_skill_scaffold(
            skill_name=args.name,
            viral_story_path=Path(args.viral_story),
            new_story_idea_path=Path(args.new_story_idea),
            out_path=Path(args.out),
        )
        print(f"[OK] Wrote skill scaffold to {out_path}")
        return
    raise ValueError("skill command requires one of: list, show, export, scaffold")
```

- [ ] **Step 5: Run the parser tests and verify they pass**

Run: `python -m unittest tests.test_skill_assets.SkillAssetsTests.test_parser_accepts_skill_subcommands tests.test_skill_assets.SkillAssetsTests.test_parser_accepts_skill_scaffold_arguments -v`

Expected: PASS.

- [ ] **Step 6: Run the full new skill test file**

Run: `python -m unittest tests.test_skill_assets -v`

Expected: PASS.

- [ ] **Step 7: Commit the CLI wiring**

```bash
git add src/template_novel_engine/cli.py tests/test_skill_assets.py
git commit -m "feat: add skill cli commands"
```

### Task 5: Clean up `generate` help text regression coverage

**Files:**
- Modify: `tests/test_remix_bundle.py`
- Modify: `src/template_novel_engine/cli.py`
- Test: `tests/test_remix_bundle.py`

- [ ] **Step 1: Tighten the existing parser test to cover the current help text contract**

Update `test_generate_parser_exposes_only_remix_bundle_entry` so it still checks `--remix-bundle` is present and additionally confirms the help text no longer contains `--story-idea` after parser construction.

Use this assertion block:

```python
        self.assertIn("--remix-bundle", help_text)
        self.assertNotIn("--story-idea", help_text)
        self.assertNotIn("新故事思路", help_text)
```

- [ ] **Step 2: Remove the dead `--story-idea` registration from `cli.py`**

Delete this block entirely from the `generate` parser:

```python
    gen.add_argument(
        "--story-idea",
        required=False,
        default="",
        help="Optional story idea markdown path. Default fallback: 新故事思路.md (root/inputs) -> story_idea.md (root/inputs).",
    )
```

Also delete the later removal branch:

```python
        if "--story-idea" in action.option_strings:
            _remove_option(gen, action)
```

- [ ] **Step 3: Run the targeted remix parser test**

Run: `python -m unittest tests.test_remix_bundle.RemixBundleGenerateFlowTests.test_generate_parser_exposes_only_remix_bundle_entry -v`

Expected: PASS.

- [ ] **Step 4: Commit the parser cleanup**

```bash
git add src/template_novel_engine/cli.py tests/test_remix_bundle.py
git commit -m "refactor: remove legacy generate story idea option"
```

### Task 6: Document the built-in skill workflow

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a new quick-start subsection after the remix bundle preparation section**

Insert content like this near section 4.1/4.2 so the workflow stays near `generate`:

```md
### 4.1.1 在项目内使用内置 skill

项目已内置 `viral-story-remix`，可以直接查看或导出：

```powershell
python .\main.py skill list
python .\main.py skill show viral-story-remix
python .\main.py skill export viral-story-remix --out .\outputs\viral-story-remix.SKILL.md
```

也可以把素材组装成一个给模型使用的执行包：

```powershell
python .\main.py skill scaffold viral-story-remix --viral-story .\inputs\viral_story.md --new-story-idea .\inputs\new_story_idea.md --out .\inputs\viral_story_remix_prompt.md
```

把这个 markdown 执行包交给模型后，将模型输出保存为 `inputs/remix_bundle.md` 或 `inputs/remix_bundle.json`，再执行：

```powershell
python .\main.py generate --count 20
```
```

- [ ] **Step 2: Verify README text matches the actual command names**

Check that the README uses:

- `skill list`
- `skill show viral-story-remix`
- `skill export viral-story-remix --out ...`
- `skill scaffold viral-story-remix --viral-story ... --new-story-idea ... --out ...`

- [ ] **Step 3: Commit the docs update**

```bash
git add README.md
git commit -m "docs: add built-in skill workflow"
```

### Task 7: Run regression verification before completion

**Files:**
- Test: `tests/test_skill_assets.py`
- Test: `tests/test_remix_bundle.py`

- [ ] **Step 1: Run the focused test suite**

Run: `python -m unittest tests.test_skill_assets tests.test_remix_bundle -v`

Expected: PASS for the new skill tests and existing remix bundle tests.

- [ ] **Step 2: Run key CLI smoke checks**

Run: `python .\main.py skill list`

Expected output includes:

```text
viral-story-remix
```

Run: `python .\main.py skill show viral-story-remix`

Expected output includes:

```text
name: viral-story-remix
```

- [ ] **Step 3: Inspect the resulting diff**

Run: `git diff -- src/template_novel_engine/skill_assets.py src/template_novel_engine/cli.py src/template_novel_engine/skills/viral-story-remix/SKILL.md tests/test_skill_assets.py tests/test_remix_bundle.py README.md`

Expected: only the planned files and changes appear.

- [ ] **Step 4: Commit the final verified state**

```bash
git add src/template_novel_engine/skill_assets.py src/template_novel_engine/cli.py src/template_novel_engine/skills/viral-story-remix/SKILL.md tests/test_skill_assets.py tests/test_remix_bundle.py README.md
git commit -m "feat: integrate built-in remix skill into cli"
```

## Self-Review

- Spec coverage check: the plan covers vendoring the skill, adding a helper module, wiring `skill list/show/export/scaffold`, preserving `generate`, adding tests, and documenting the workflow.
- Placeholder scan: no `TODO`, `TBD`, or deferred implementation markers remain.
- Type consistency: the plan uses one consistent helper API (`list_skill_names`, `get_skill_text`, `export_skill`, `build_skill_scaffold`) and one CLI namespace (`skill_command`, `name`, `viral_story`, `new_story_idea`, `out`).

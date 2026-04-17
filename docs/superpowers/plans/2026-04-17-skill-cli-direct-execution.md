# Skill CLI Direct Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `skill scaffold` so it directly calls the configured LLM writer and produces a validated `inputs/remix_bundle.md` instead of only writing a prompt package.

**Architecture:** Reuse the existing writer configuration and backend HTTP logic by adding one small generic text-generation function in `model_writer.py`, then route `skill scaffold` through `skill_assets.py` to build the prompt, call the LLM, validate the returned markdown via `load_remix_bundle()`, and write the final result file. Keep `generate` unchanged so it continues to consume the resulting bundle.

**Tech Stack:** Python 3, argparse, pathlib, tempfile, unittest, urllib

---

## File Map

- Modify: `src/template_novel_engine/model_writer.py`
  Purpose: add a generic LLM text-generation entry point that reuses existing backend plumbing.
- Modify: `src/template_novel_engine/skill_assets.py`
  Purpose: replace prompt-only scaffold behavior with direct execution, validation, and output writing.
- Modify: `src/template_novel_engine/cli.py`
  Purpose: pass writer settings into `skill scaffold`, set default output path, and keep help text aligned.
- Modify: `tests/test_skill_assets.py`
  Purpose: cover direct execution, builtin rejection, validation failure, and parser defaults.
- Modify: `README.md`
  Purpose: document that `skill scaffold` now directly produces `remix_bundle.md`.

### Task 1: Replace prompt-only tests with failing direct-execution tests

**Files:**
- Modify: `tests/test_skill_assets.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Rewrite the skill test file to target direct execution behavior**

Replace `tests/test_skill_assets.py` with:

```python
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from template_novel_engine.app_config import load_runtime_config
from template_novel_engine.cli import _build_parser
from template_novel_engine.skill_assets import (
    build_skill_prompt,
    execute_skill_scaffold,
    export_skill,
    get_skill_text,
    list_skill_names,
)


def _sample_bundle_markdown() -> str:
    return """## Remix Bundle JSON
```json
{
  "schema_version": "remix_bundle.v1",
  "project_brief": {
    "title": "测试新书",
    "genre": "都市",
    "tone": "强情绪",
    "episode_count": 20,
    "target_length": "约2万字",
    "must_keep": ["女主重生"],
    "forbidden": ["照抄原剧情"],
    "core_hook": "重生当天反杀订婚局",
    "core_payoff": "拿回人生主动权"
  },
  "source_trace": {
    "viral_story_title": "爆款参考",
    "new_story_title": "新故事",
    "migration_focus": "迁移强钩子和升级链路",
    "retained_elements": ["重生", "复仇"]
  },
  "template_dna": {
    "schema_version": "v1",
    "source_file": "skill://viral-story-remix",
    "core_premise": "主角在羞辱局中翻盘并持续升级",
    "template_formulas": ["开局被压制后反打"],
    "narrative_stages": [
      {"stage": "1", "focus": "开局受压"},
      {"stage": "2", "focus": "第一次翻盘"},
      {"stage": "3", "focus": "扩大冲突"},
      {"stage": "4", "focus": "终局决战"}
    ],
    "rhythm_beats": [
      {"chapters": "1-5", "beat": "受压"},
      {"chapters": "6-10", "beat": "反击"},
      {"chapters": "11-15", "beat": "升级"},
      {"chapters": "16-20", "beat": "决战"}
    ],
    "dialogue_patterns": ["短句对撞"],
    "principles": [
      {"detail": "主角主体性不能丢"},
      {"detail": "兑现点必须分阶段出现"},
      {"detail": "不能提前消耗终局高潮"}
    ],
    "reusable_motifs": ["公开打脸"]
  },
  "story_bible": {
    "schema_version": "v1",
    "source_file": "skill://viral-story-remix",
    "metadata": {
      "title": "测试新书",
      "genre": "都市",
      "tone": "强情绪",
      "protagonist_name": "沈昭",
      "target_chapters": 20,
      "chapter_word_target": 800
    },
    "premise": {
      "logline": "沈昭重生回订婚羞辱夜，开始反杀。",
      "theme": "夺回命运",
      "selling_points": ["重生", "复仇", "反转"]
    },
    "world": {
      "era": "现代",
      "locations": ["江城", "顾家"],
      "rules": ["豪门舆论决定资源"],
      "power_system": "资本与人脉"
    },
    "characters": [
      {"name": "沈昭", "role": "主角", "goal": "复仇", "flaw": "过于孤决", "arc": "学会借力"},
      {"name": "顾承", "role": "主要对手", "goal": "压制沈昭", "flaw": "傲慢", "arc": "失控坠落"},
      {"name": "林岚", "role": "盟友", "goal": "帮助主角", "flaw": "曾经软弱", "arc": "站出来"}
    ],
    "factions": ["顾家", "沈家"],
    "conflicts": {
      "main_conflict": "沈昭与顾承的正面对抗",
      "secondary_conflicts": ["家族压力", "舆论围剿"]
    },
    "constraints": {
      "must_have": ["强钩子"],
      "must_avoid": ["换皮照抄"]
    }
  },
  "structure_map": {
    "schema_version": "v1",
    "book_title": "测试新书",
    "target_chapters": 20,
    "stage_contracts": [
      {"stage_id": "S1", "template_title": "开局受压", "chapter_start": 1, "chapter_end": 5, "story_goal": "压低主角", "must_keep": ["羞辱局"], "escalation_target": "第一次反击", "pov_focus": "沈昭", "setpiece_candidates": ["订婚宴"]},
      {"stage_id": "S2", "template_title": "首次翻盘", "chapter_start": 6, "chapter_end": 10, "story_goal": "主角赢回一局", "must_keep": ["打脸"], "escalation_target": "敌方报复", "pov_focus": "沈昭", "setpiece_candidates": ["记者会"]},
      {"stage_id": "S3", "template_title": "战场扩大", "chapter_start": 11, "chapter_end": 15, "story_goal": "冲突升级", "must_keep": ["更高赌注"], "escalation_target": "终局铺垫", "pov_focus": "沈昭", "setpiece_candidates": ["董事会"]},
      {"stage_id": "S4", "template_title": "终局决战", "chapter_start": 16, "chapter_end": 20, "story_goal": "完成清算", "must_keep": ["终局反杀"], "escalation_target": "价值落点", "pov_focus": "沈昭", "setpiece_candidates": ["公开审判"]}
    ],
    "chapter_plan": [
      {"chapter": 1, "title": "回到羞辱夜", "stage_id": "S1", "objective": "沈昭在订婚宴上意识到自己重生并开始布局。"},
      {"chapter": 2, "title": "留证", "stage_id": "S1", "objective": "沈昭收集顾承设局证据并稳住局面。"},
      {"chapter": 3, "title": "试探", "stage_id": "S1", "objective": "沈昭试探盟友立场，避免再次孤立。"},
      {"chapter": 4, "title": "逼近爆点", "stage_id": "S1", "objective": "沈昭把顾承推到必须出手的边缘。"},
      {"chapter": 5, "title": "第一记耳光", "stage_id": "S1", "objective": "沈昭完成第一次公开反击。"},
      {"chapter": 6, "title": "舆论反扑", "stage_id": "S2", "objective": "顾承发动舆论战，沈昭决定正面应对。"},
      {"chapter": 7, "title": "记者会", "stage_id": "S2", "objective": "沈昭在记者会上扭转舆论走向。"},
      {"chapter": 8, "title": "盟友归位", "stage_id": "S2", "objective": "林岚站队并提供关键资源。"},
      {"chapter": 9, "title": "敌人的软肋", "stage_id": "S2", "objective": "沈昭锁定顾承更深层弱点。"},
      {"chapter": 10, "title": "赢回一城", "stage_id": "S2", "objective": "沈昭拿下阶段性胜利并逼出更大敌人。"},
      {"chapter": 11, "title": "新战场", "stage_id": "S3", "objective": "冲突从私域扩大到公司层面。"},
      {"chapter": 12, "title": "高层博弈", "stage_id": "S3", "objective": "沈昭第一次参与高层博弈并显露手段。"},
      {"chapter": 13, "title": "旧账翻出", "stage_id": "S3", "objective": "旧日真相浮现，赌注升级。"},
      {"chapter": 14, "title": "代价", "stage_id": "S3", "objective": "沈昭为强行推进付出重大代价。"},
      {"chapter": 15, "title": "决战前夜", "stage_id": "S3", "objective": "主角完成终局部署。"},
      {"chapter": 16, "title": "公开审判", "stage_id": "S4", "objective": "终局对抗正式开始。"},
      {"chapter": 17, "title": "层层反转", "stage_id": "S4", "objective": "敌我底牌逐步掀开。"},
      {"chapter": 18, "title": "真正主谋", "stage_id": "S4", "objective": "沈昭锁定更高层真相。"},
      {"chapter": 19, "title": "终局反杀", "stage_id": "S4", "objective": "沈昭完成最后反击。"},
      {"chapter": 20, "title": "新生", "stage_id": "S4", "objective": "故事完成价值落点，主角拿回人生。"}
    ]
  },
  "human_readable_markdown": "## 简短分析\n- 继承强钩子与升级链路。\n\n## 爆点映射\n- 原爆款钩子 -> 新钩子\n- 原冤屈结构 -> 新冤屈结构\n- 原护道者功能 -> 新护道者功能\n- 原升级链路 -> 新升级链路\n- 原价值落点 -> 新价值落点\n\n## 新故事大纲\n### 故事总纲\n沈昭重生后反杀订婚羞辱局。\n\n### 分阶段弧线\n- 1-5：受压与首次反击\n- 6-10：翻盘与扩大胜势\n- 11-15：战场扩大与决战铺垫\n- 16-20：终局清算\n\n### 分集大纲\n第1集\n开场局面：订婚羞辱夜\n核心事件：沈昭重生\n冲突推进：顾承施压\n关键场面：\n  场面一：订婚宴失控\n  场面二：沈昭暗中留证\n情绪变化：惊怒转冷静\n爆点/反转：她决定不再忍\n结尾卡点：她拿到关键证据"
}
```

## Companion Markdown
## 简短分析
- 继承强钩子与升级链路。

## 爆点映射
- 原爆款钩子 -> 新钩子
- 原冤屈结构 -> 新冤屈结构
- 原护道者功能 -> 新护道者功能
- 原升级链路 -> 新升级链路
- 原价值落点 -> 新价值落点

## 新故事大纲
### 故事总纲
沈昭重生后反杀订婚羞辱局。

### 分阶段弧线
- 1-5：受压与首次反击
- 6-10：翻盘与扩大胜势
- 11-15：战场扩大与决战铺垫
- 16-20：终局清算

### 分集大纲
第1集
开场局面：订婚羞辱夜
核心事件：沈昭重生
冲突推进：顾承施压
关键场面：
  场面一：订婚宴失控
  场面二：沈昭暗中留证
情绪变化：惊怒转冷静
爆点/反转：她决定不再忍
结尾卡点：她拿到关键证据
"""


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

    def test_build_skill_prompt_contains_skill_and_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            viral_story_path = root / "viral_story.md"
            new_story_idea_path = root / "new_story_idea.md"
            viral_story_path.write_text("爆款故事原文", encoding="utf-8")
            new_story_idea_path.write_text("新故事思路", encoding="utf-8")

            system_prompt, user_prompt = build_skill_prompt(
                skill_name="viral-story-remix",
                viral_story_path=viral_story_path,
                new_story_idea_path=new_story_idea_path,
            )

            self.assertIn("strictly", system_prompt.lower())
            self.assertIn("## SKILL.md", user_prompt)
            self.assertIn("## Input: viral_story\n爆款故事原文", user_prompt)
            self.assertIn("## Input: new_story_idea\n新故事思路", user_prompt)

    def test_execute_skill_scaffold_rejects_builtin_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            viral_story_path = root / "viral_story.md"
            new_story_idea_path = root / "new_story_idea.md"
            out_path = root / "remix_bundle.md"
            viral_story_path.write_text("爆款故事原文", encoding="utf-8")
            new_story_idea_path.write_text("新故事思路", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "requires openai/claude"):
                execute_skill_scaffold(
                    skill_name="viral-story-remix",
                    viral_story_path=viral_story_path,
                    new_story_idea_path=new_story_idea_path,
                    out_path=out_path,
                    writer_config={"backend": "builtin"},
                )

    @patch("template_novel_engine.skill_assets.generate_text_with_llm")
    def test_execute_skill_scaffold_writes_valid_bundle_markdown(self, mock_generate_text) -> None:
        mock_generate_text.return_value = (_sample_bundle_markdown(), {"backend": "openai", "model": "test-model"})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            viral_story_path = root / "viral_story.md"
            new_story_idea_path = root / "new_story_idea.md"
            out_path = root / "remix_bundle.md"
            viral_story_path.write_text("爆款故事原文", encoding="utf-8")
            new_story_idea_path.write_text("新故事思路", encoding="utf-8")

            result_path = execute_skill_scaffold(
                skill_name="viral-story-remix",
                viral_story_path=viral_story_path,
                new_story_idea_path=new_story_idea_path,
                out_path=out_path,
                writer_config={"backend": "openai", "model": "test-model", "api_key": "test-key", "max_tokens": 6000, "timeout_sec": 30},
            )

            self.assertEqual(result_path, out_path)
            self.assertTrue(out_path.exists())
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("## Remix Bundle JSON", content)
            self.assertIn("## Companion Markdown", content)

    @patch("template_novel_engine.skill_assets.generate_text_with_llm")
    def test_execute_skill_scaffold_rejects_invalid_bundle_output(self, mock_generate_text) -> None:
        mock_generate_text.return_value = ("普通闲聊文本", {"backend": "openai", "model": "test-model"})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            viral_story_path = root / "viral_story.md"
            new_story_idea_path = root / "new_story_idea.md"
            out_path = root / "remix_bundle.md"
            viral_story_path.write_text("爆款故事原文", encoding="utf-8")
            new_story_idea_path.write_text("新故事思路", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "valid remix bundle"):
                execute_skill_scaffold(
                    skill_name="viral-story-remix",
                    viral_story_path=viral_story_path,
                    new_story_idea_path=new_story_idea_path,
                    out_path=out_path,
                    writer_config={"backend": "openai", "model": "test-model", "api_key": "test-key", "max_tokens": 6000, "timeout_sec": 30},
                )

            self.assertFalse(out_path.exists())

    def test_parser_accepts_skill_subcommands(self) -> None:
        runtime_cfg = load_runtime_config(PROJECT_ROOT)
        parser = _build_parser(PROJECT_ROOT, runtime_cfg)

        args = parser.parse_args(["skill", "show", "viral-story-remix"])

        self.assertEqual(args.command, "skill")
        self.assertEqual(args.skill_command, "show")
        self.assertEqual(args.name, "viral-story-remix")

    def test_parser_skill_scaffold_defaults_output_to_inputs_bundle(self) -> None:
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
            ]
        )

        self.assertEqual(args.command, "skill")
        self.assertEqual(args.skill_command, "scaffold")
        self.assertEqual(args.name, "viral-story-remix")
        self.assertEqual(args.viral_story, "viral_story.md")
        self.assertEqual(args.new_story_idea, "new_story_idea.md")
        self.assertEqual(args.out, str(PROJECT_ROOT / "inputs" / "remix_bundle.md"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new skill test file and verify it fails**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: FAIL because `build_skill_prompt`, `execute_skill_scaffold`, and the new parser default behavior do not exist yet.

- [ ] **Step 3: Commit the failing test update**

```bash
git add tests/test_skill_assets.py
git commit -m "test: define direct skill execution behavior"
```

### Task 2: Add a generic LLM text-generation entry point

**Files:**
- Modify: `src/template_novel_engine/model_writer.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Add the minimal public helper after `writer_public_profile()`**

Insert:

```python
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
```

- [ ] **Step 2: Run the skill tests and verify they still fail, but no longer on missing helper import**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: FAIL in `skill_assets` behavior and parser behavior, not because `generate_text_with_llm` is undefined.

- [ ] **Step 3: Commit the generic helper**

```bash
git add src/template_novel_engine/model_writer.py
git commit -m "feat: add generic llm text generation helper"
```

### Task 3: Convert `skill_assets.py` to direct execution with validation

**Files:**
- Modify: `src/template_novel_engine/skill_assets.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Replace the current prompt-only helper implementation**

Rewrite `src/template_novel_engine/skill_assets.py` to:

```python
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from .model_writer import generate_text_with_llm, normalize_writer_config
from .remix_bundle import load_remix_bundle


_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_SYSTEM_PROMPT = (
    "You are executing a project-owned writing skill. "
    "Follow the provided contract exactly and return only the required result sections."
)
_EXECUTION_INSTRUCTION = (
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
    _validate_bundle_markdown(raw_text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(raw_text, encoding="utf-8")
    return out_path


def _validate_bundle_markdown(content: str) -> None:
    if "## Remix Bundle JSON" not in content or "## Companion Markdown" not in content:
        raise ValueError("LLM output is not a valid remix bundle")
    with tempfile.TemporaryDirectory() as tmp:
        temp_path = Path(tmp) / "remix_bundle.md"
        temp_path.write_text(content, encoding="utf-8")
        try:
            load_remix_bundle(temp_path)
        except Exception as exc:
            raise ValueError("LLM output is not a valid remix bundle") from exc


def _read_required_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Input file is empty: {path}")
    return text
```

- [ ] **Step 2: Run the skill test file and verify the new execution tests pass**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: PASS for the updated direct-execution tests.

- [ ] **Step 3: Commit the direct execution module**

```bash
git add src/template_novel_engine/skill_assets.py tests/test_skill_assets.py
git commit -m "feat: execute built-in remix skill through llm"
```

### Task 4: Wire `skill scaffold` through CLI writer config and default output

**Files:**
- Modify: `src/template_novel_engine/cli.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Update imports in `cli.py`**

Replace the current `skill_assets` import with:

```python
from .skill_assets import execute_skill_scaffold, export_skill, get_skill_text, list_skill_names
```

- [ ] **Step 2: Update the parser block for `skill scaffold`**

Replace the current scaffold parser section with:

```python
    skill_scaffold = skill_sub.add_parser("scaffold", help="Execute a built-in skill and build a remix bundle.")
    skill_scaffold.add_argument("name", help="Built-in skill name.")
    skill_scaffold.add_argument("--viral-story", required=True, help="Input viral story path.")
    skill_scaffold.add_argument("--new-story-idea", required=True, help="Input new story idea path.")
    skill_scaffold.add_argument(
        "--out",
        required=False,
        default=str(project_root_default / "inputs" / "remix_bundle.md"),
        help="Output remix bundle markdown path. Default: <project-root>/inputs/remix_bundle.md",
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
    skill_scaffold.add_argument("--writer-max-tokens", required=False, type=int, default=int(writer_defaults.get("max_tokens", 2200)))
    skill_scaffold.add_argument("--writer-timeout-sec", required=False, type=int, default=int(writer_defaults.get("timeout_sec", 120)))
    skill_scaffold.add_argument("--writer-system-prompt-file", required=False, default=str(writer_defaults.get("system_prompt_file", "")))
```

- [ ] **Step 3: Update `_run_skill_command()` scaffold branch**

Replace the scaffold branch with:

```python
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
```

- [ ] **Step 4: Run the skill test file again**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: PASS, including parser default output assertions.

- [ ] **Step 5: Commit the CLI wiring**

```bash
git add src/template_novel_engine/cli.py tests/test_skill_assets.py
git commit -m "feat: wire skill scaffold to writer config"
```

### Task 5: Update README to match direct execution

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the prompt-packaging description with direct execution language**

Update the skill section so it reads like this:

```md
也可以直接让项目内置 skill 生成 `remix_bundle.md`：

```powershell
python .\main.py skill scaffold viral-story-remix --viral-story .\inputs\viral_story.md --new-story-idea .\inputs\new_story_idea.md
```

如果已配置 `writer`，这个命令会直接调用模型，并默认写出：

- `inputs/remix_bundle.md`

随后执行：

```powershell
python .\main.py generate --count 20
```
```

- [ ] **Step 2: Remove or rewrite any wording that says `skill scaffold` only creates a prompt package**

Ensure the README no longer claims that the command merely prepares markdown for an external model handoff.

- [ ] **Step 3: Commit the docs update**

```bash
git add README.md
git commit -m "docs: describe direct skill execution workflow"
```

### Task 6: Run focused verification before completion

**Files:**
- Test: `tests/test_skill_assets.py`
- Test: `tests/test_remix_bundle.py`

- [ ] **Step 1: Run the updated skill test suite**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: PASS for all updated direct-execution tests.

- [ ] **Step 2: Run remix bundle regressions**

Run: `python -m unittest discover -s tests -p "test_remix_bundle.py" -v`

Expected: PASS, proving `generate` remains unchanged and bundle-driven.

- [ ] **Step 3: Run CLI parser smoke checks**

Run: `python .\main.py skill list`

Expected output includes:

```text
viral-story-remix
```

Run: `python .\main.py skill scaffold --help`

Expected output includes:

```text
--writer-backend
--viral-story
--new-story-idea
remix_bundle.md
```

- [ ] **Step 4: Inspect the resulting diff**

Run: `git diff -- src/template_novel_engine/model_writer.py src/template_novel_engine/skill_assets.py src/template_novel_engine/cli.py tests/test_skill_assets.py tests/test_remix_bundle.py README.md`

Expected: only the planned files and related changes appear.

- [ ] **Step 5: Commit the final verified state**

```bash
git add src/template_novel_engine/model_writer.py src/template_novel_engine/skill_assets.py src/template_novel_engine/cli.py tests/test_skill_assets.py tests/test_remix_bundle.py README.md
git commit -m "feat: execute remix skill directly from cli"
```

## Self-Review

- Spec coverage check: the plan covers direct execution behavior, default output path, writer reuse, backend restrictions, validation through `load_remix_bundle()`, tests, and README updates.
- Placeholder scan: no `TODO`, `TBD`, or unresolved references remain.
- Type consistency: the plan uses one consistent new API surface: `build_skill_prompt()`, `execute_skill_scaffold()`, and `generate_text_with_llm()`.

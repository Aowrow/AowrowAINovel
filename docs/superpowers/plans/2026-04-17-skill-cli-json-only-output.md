# Skill CLI JSON-Only Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change built-in `viral-story-remix` execution so `skill scaffold` produces only a validated `remix_bundle.json` and no longer requests, validates, or saves companion markdown.

**Architecture:** Update the built-in skill contract to require one JSON object only, then update `skill_assets.py` and `cli.py` to request JSON-only output and save it to `inputs/remix_bundle.json`. Relax remix bundle validation so `human_readable_markdown` is optional or may be empty, which keeps `generate` compatible with JSON-only bundles.

**Tech Stack:** Python 3, argparse, json, pathlib, unittest, unittest.mock

---

## File Map

- Modify: `src/template_novel_engine/skills/viral-story-remix/SKILL.md`
  Purpose: change the skill output contract from JSON+Markdown to JSON only.
- Modify: `src/template_novel_engine/skill_assets.py`
  Purpose: request JSON-only output, validate decoded JSON, save `remix_bundle.json`, and keep raw failure dumps.
- Modify: `src/template_novel_engine/cli.py`
  Purpose: make `skill scaffold` default to `inputs/remix_bundle.json` and fix help text.
- Modify: `src/template_novel_engine/remix_bundle.py`
  Purpose: stop requiring non-empty `human_readable_markdown` so JSON-only bundles validate.
- Modify: `tests/test_skill_assets.py`
  Purpose: cover JSON-only output, default JSON path, invalid JSON rejection, and raw dump behavior.
- Modify: `tests/test_remix_bundle.py`
  Purpose: cover JSON-only bundle validation when `human_readable_markdown` is empty.
- Modify: `README.md`
  Purpose: document JSON-only `skill scaffold` output.

### Task 1: Rewrite tests to require JSON-only output

**Files:**
- Modify: `tests/test_skill_assets.py`
- Modify: `tests/test_remix_bundle.py`
- Test: `tests/test_skill_assets.py`
- Test: `tests/test_remix_bundle.py`

- [ ] **Step 1: Update `tests/test_skill_assets.py` assertions from markdown output to JSON output**

Make these exact replacements:

1. In `_sample_bundle_markdown()`, rename it to `_sample_bundle_json_text()`.
2. Replace the function body with:

```python
def _sample_bundle_json_text() -> str:
    payload = {
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
            "core_payoff": "拿回人生主动权",
        },
        "source_trace": {
            "viral_story_title": "爆款参考",
            "new_story_title": "新故事",
            "migration_focus": "迁移强钩子和升级链路",
            "retained_elements": ["重生", "复仇"],
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
                {"stage": "4", "focus": "终局决战"},
            ],
            "rhythm_beats": [
                {"chapters": "1-5", "beat": "受压"},
                {"chapters": "6-10", "beat": "反击"},
                {"chapters": "11-15", "beat": "升级"},
                {"chapters": "16-20", "beat": "决战"},
            ],
            "dialogue_patterns": ["短句对撞"],
            "principles": [
                {"detail": "主角主体性不能丢"},
                {"detail": "兑现点必须分阶段出现"},
                {"detail": "不能提前消耗终局高潮"},
            ],
            "reusable_motifs": ["公开打脸"],
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
                "chapter_word_target": 800,
            },
            "premise": {
                "logline": "沈昭重生回订婚羞辱夜，开始反杀。",
                "theme": "夺回命运",
                "selling_points": ["重生", "复仇", "反转"],
            },
            "world": {
                "era": "现代",
                "locations": ["江城", "顾家"],
                "rules": ["豪门舆论决定资源"],
                "power_system": "资本与人脉",
            },
            "characters": [
                {"name": "沈昭", "role": "主角", "goal": "复仇", "flaw": "过于孤决", "arc": "学会借力"},
                {"name": "顾承", "role": "主要对手", "goal": "压制沈昭", "flaw": "傲慢", "arc": "失控坠落"},
                {"name": "林岚", "role": "盟友", "goal": "帮助主角", "flaw": "曾经软弱", "arc": "站出来"},
            ],
            "factions": ["顾家", "沈家"],
            "conflicts": {
                "main_conflict": "沈昭与顾承的正面对抗",
                "secondary_conflicts": ["家族压力", "舆论围剿"],
            },
            "constraints": {
                "must_have": ["强钩子"],
                "must_avoid": ["换皮照抄"],
            },
        },
        "structure_map": {
            "schema_version": "v1",
            "book_title": "测试新书",
            "target_chapters": 20,
            "stage_contracts": [
                {"stage_id": "S1", "template_title": "开局受压", "chapter_start": 1, "chapter_end": 5, "story_goal": "压低主角", "must_keep": ["羞辱局"], "escalation_target": "第一次反击", "pov_focus": "沈昭", "setpiece_candidates": ["订婚宴"]},
                {"stage_id": "S2", "template_title": "首次翻盘", "chapter_start": 6, "chapter_end": 10, "story_goal": "主角赢回一局", "must_keep": ["打脸"], "escalation_target": "敌方报复", "pov_focus": "沈昭", "setpiece_candidates": ["记者会"]},
                {"stage_id": "S3", "template_title": "战场扩大", "chapter_start": 11, "chapter_end": 15, "story_goal": "冲突升级", "must_keep": ["更高赌注"], "escalation_target": "终局铺垫", "pov_focus": "沈昭", "setpiece_candidates": ["董事会"]},
                {"stage_id": "S4", "template_title": "终局决战", "chapter_start": 16, "chapter_end": 20, "story_goal": "完成清算", "must_keep": ["终局反杀"], "escalation_target": "价值落点", "pov_focus": "沈昭", "setpiece_candidates": ["公开审判"]},
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
                {"chapter": 20, "title": "新生", "stage_id": "S4", "objective": "故事完成价值落点，主角拿回人生。"},
            ],
        },
        "human_readable_markdown": "",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
```

3. In `test_execute_skill_scaffold_writes_valid_bundle_markdown`, rename the test to `test_execute_skill_scaffold_writes_valid_bundle_json`.
4. Change `out_path = root / "remix_bundle.md"` to `out_path = root / "remix_bundle.json"`.
5. Change `mock_generate_text.return_value = (_sample_bundle_markdown(), ...)` to `mock_generate_text.return_value = (_sample_bundle_json_text(), ...)`.
6. Replace:

```python
            self.assertIn("## Remix Bundle JSON", content)
            self.assertIn("## Companion Markdown", content)
```

with:

```python
            payload = json.loads(content)
            self.assertEqual(payload["schema_version"], "remix_bundle.v1")
            self.assertEqual(payload["story_bible"]["metadata"]["title"], "测试新书")
```

7. In `test_execute_skill_scaffold_rejects_invalid_bundle_output`, change `out_path = root / "remix_bundle.md"` to `out_path = root / "remix_bundle.json"`.
8. Change `raw_path = root / "remix_bundle.raw.md"` to `raw_path = root / "remix_bundle.raw.json"`.
9. In `test_parser_skill_scaffold_defaults_output_to_inputs_bundle`, replace:

```python
        self.assertEqual(args.out, str(PROJECT_ROOT / "inputs" / "remix_bundle.md"))
```

with:

```python
        self.assertEqual(args.out, str(PROJECT_ROOT / "inputs" / "remix_bundle.json"))
```

- [ ] **Step 2: Add a remix bundle regression test that allows empty `human_readable_markdown`**

In `tests/test_remix_bundle.py`, add this method under `RemixBundleContractTests`:

```python
    def test_load_remix_bundle_allows_empty_human_readable_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remix_bundle.json"
            payload = _sample_bundle()
            payload["human_readable_markdown"] = ""
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            bundle = load_remix_bundle(path)

            self.assertEqual(bundle["schema_version"], "remix_bundle.v1")
            self.assertEqual(bundle["human_readable_markdown"], "")
```

- [ ] **Step 3: Run the two focused test files and verify they fail**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: FAIL because the current implementation still writes markdown and raw `.md` files.

Run: `python -m unittest discover -s tests -p "test_remix_bundle.py" -v`

Expected: FAIL because `validate_remix_bundle()` still requires non-empty `human_readable_markdown`.

- [ ] **Step 4: Commit the failing JSON-only tests**

```bash
git add tests/test_skill_assets.py tests/test_remix_bundle.py
git commit -m "test: define json-only remix skill output"
```

### Task 2: Relax remix bundle validation for JSON-only output

**Files:**
- Modify: `src/template_novel_engine/remix_bundle.py`
- Test: `tests/test_remix_bundle.py`

- [ ] **Step 1: Replace the strict `human_readable_markdown` requirement**

In `src/template_novel_engine/remix_bundle.py`, replace:

```python
    _expect_nonempty_str(bundle.get("human_readable_markdown"), "human_readable_markdown")
```

with:

```python
    human_readable = bundle.get("human_readable_markdown", "")
    if human_readable is None:
        bundle["human_readable_markdown"] = ""
    elif not isinstance(human_readable, str):
        raise ValueError("human_readable_markdown must be a string")
    else:
        bundle["human_readable_markdown"] = human_readable
```

- [ ] **Step 2: Run the remix bundle tests and verify the new regression passes**

Run: `python -m unittest discover -s tests -p "test_remix_bundle.py" -v`

Expected: PASS for all remix bundle tests, including the empty `human_readable_markdown` case.

- [ ] **Step 3: Commit the validation relaxation**

```bash
git add src/template_novel_engine/remix_bundle.py tests/test_remix_bundle.py
git commit -m "fix: allow json-only remix bundles"
```

### Task 3: Change the built-in skill contract to JSON only

**Files:**
- Modify: `src/template_novel_engine/skills/viral-story-remix/SKILL.md`

- [ ] **Step 1: Rewrite the output contract section headings and rules**

Make these exact content changes in `SKILL.md`:

1. Replace:

```md
最终输出只能有两个顶层区块，顺序固定：

1. `## Remix Bundle JSON`
2. `## Companion Markdown`

不允许在这两个区块前后加解释、寒暄、免责声明、提示词说明。
```

with:

```md
最终输出只能是一个合法 JSON 对象。

不允许在 JSON 前后加解释、寒暄、免责声明、提示词说明、Markdown 标题、代码围栏。
```

2. Replace the section heading:

```md
### 1. `## Remix Bundle JSON`
```

with:

```md
### Final JSON Payload
```

3. Delete the entire `### 2. ## Companion Markdown` section.
4. Replace the `human_readable_markdown` requirement text with:

```md
#### `human_readable_markdown`

必须是字符串字段。

允许为空字符串：

```json
"human_readable_markdown": ""
```

如果填写内容，也只能是简短的人类可读摘要；不再要求 companion markdown 镜像结构。
```

5. In `## Self Check`, replace:

```md
- 顶层只有两个区块：`## Remix Bundle JSON`、`## Companion Markdown`。
```

with:

```md
- 最终输出只有一个合法 JSON 对象，没有 markdown 包装。
```

6. Replace:

```md
- human_readable_markdown 与 Companion Markdown 一致。
```

with:

```md
- human_readable_markdown 是字符串；可为空。
```

7. Replace:

```md
- 输出必须先给 JSON，再给 Markdown。
```

with:

```md
- 输出必须直接给 JSON 对象。
```

- [ ] **Step 2: Review the skill file for leftover companion-markdown instructions**

Search the file for these strings and remove any stale references:

- `Companion Markdown`
- `## 简短分析`
- `## 爆点映射`
- `## 新故事大纲`

- [ ] **Step 3: Commit the skill contract update**

```bash
git add src/template_novel_engine/skills/viral-story-remix/SKILL.md
git commit -m "docs: switch remix skill contract to json only"
```

### Task 4: Convert skill execution and raw dumps to JSON-only files

**Files:**
- Modify: `src/template_novel_engine/skill_assets.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Update system and execution prompts to request only JSON**

In `src/template_novel_engine/skill_assets.py`, replace:

```python
_SYSTEM_PROMPT = (
    "You are executing a project-owned writing skill. "
    "Strictly follow the provided contract exactly and return only the required result sections."
)
_EXECUTION_INSTRUCTION = (
    "Strictly follow the SKILL.md below. The final output must contain only:\n"
    "1. `## Remix Bundle JSON`\n"
    "2. `## Companion Markdown`"
)
```

with:

```python
_SYSTEM_PROMPT = (
    "You are executing a project-owned writing skill. "
    "Strictly follow the provided contract exactly and return only one valid JSON object."
)
_EXECUTION_INSTRUCTION = (
    "Strictly follow the SKILL.md below. "
    "The final output must be only one valid JSON object with no markdown wrapper and no extra commentary."
)
```

- [ ] **Step 2: Replace markdown validation with JSON validation**

In `execute_skill_scaffold()`, replace:

```python
    try:
        _validate_bundle_markdown(raw_text)
    except ValueError:
        raw_path = out_path.with_suffix(".raw.md")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_text, encoding="utf-8")
        raise
```

with:

```python
    try:
        payload = _validate_bundle_json(raw_text)
    except ValueError:
        raw_path = out_path.with_suffix(".raw.json")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_text, encoding="utf-8")
        raise
```

Then replace:

```python
    out_path.write_text(raw_text, encoding="utf-8")
```

with:

```python
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 3: Add the new JSON validator and imports**

At the top of the file, add:

```python
import json
from .remix_bundle import validate_remix_bundle
```

Replace `_validate_bundle_markdown()` entirely with:

```python
def _validate_bundle_json(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM output is not a valid remix bundle JSON") from exc
    try:
        return validate_remix_bundle(payload)
    except Exception as exc:
        raise ValueError("LLM output is not a valid remix bundle JSON") from exc
```

- [ ] **Step 4: Run the skill tests and verify JSON-only behavior passes**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: PASS for JSON output file assertions and raw `.raw.json` assertions.

- [ ] **Step 5: Commit the JSON-only execution path**

```bash
git add src/template_novel_engine/skill_assets.py tests/test_skill_assets.py
git commit -m "feat: execute remix skill as json only"
```

### Task 5: Change CLI defaults and help text to JSON output

**Files:**
- Modify: `src/template_novel_engine/cli.py`
- Test: `tests/test_skill_assets.py`

- [ ] **Step 1: Change `skill scaffold` default output path and help text**

In `src/template_novel_engine/cli.py`, replace:

```python
        default=str(project_root_default / "inputs" / "remix_bundle.md"),
        help="Output remix bundle markdown path. Default: <project-root>/inputs/remix_bundle.md",
```

with:

```python
        default=str(project_root_default / "inputs" / "remix_bundle.json"),
        help="Output remix bundle JSON path. Default: <project-root>/inputs/remix_bundle.json",
```

- [ ] **Step 2: Keep the higher token default for scaffold output**

Replace:

```python
    skill_scaffold.add_argument("--writer-max-tokens", required=False, type=int, default=int(writer_defaults.get("max_tokens", 2200)))
```

with:

```python
    skill_scaffold.add_argument(
        "--writer-max-tokens",
        required=False,
        type=int,
        default=max(6000, int(writer_defaults.get("max_tokens", 2200))),
    )
```

- [ ] **Step 3: Run the skill tests again**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: PASS, including default output path and token floor assertions.

- [ ] **Step 4: Commit the CLI defaults**

```bash
git add src/template_novel_engine/cli.py tests/test_skill_assets.py
git commit -m "feat: default skill scaffold to remix_bundle json"
```

### Task 6: Update README for JSON-only output

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace markdown-output wording with JSON-output wording**

In the built-in skill section, replace:

```md
也可以直接让项目内置 skill 生成 `remix_bundle.md`：
```

with:

```md
也可以直接让项目内置 skill 生成 `remix_bundle.json`：
```

Replace:

```md
- `inputs/remix_bundle.md`
```

with:

```md
- `inputs/remix_bundle.json`
```

- [ ] **Step 2: Remove wording that says markdown is still the primary skill output**

Ensure the README no longer implies `skill scaffold` saves mixed JSON+Markdown output.

- [ ] **Step 3: Commit the docs update**

```bash
git add README.md
git commit -m "docs: describe json-only remix skill output"
```

### Task 7: Run focused verification before completion

**Files:**
- Test: `tests/test_skill_assets.py`
- Test: `tests/test_remix_bundle.py`

- [ ] **Step 1: Run the updated skill tests**

Run: `python -m unittest discover -s tests -p "test_skill_assets.py" -v`

Expected: PASS for all JSON-only skill execution tests.

- [ ] **Step 2: Run remix bundle regressions**

Run: `python -m unittest discover -s tests -p "test_remix_bundle.py" -v`

Expected: PASS, including empty `human_readable_markdown` support.

- [ ] **Step 3: Run CLI smoke checks**

Run: `python .\main.py skill list`

Expected output includes:

```text
viral-story-remix
```

Run: `python .\main.py skill scaffold --help`

Expected output includes:

```text
remix_bundle.json
--writer-max-tokens
--viral-story
--new-story-idea
```

- [ ] **Step 4: Inspect the resulting diff**

Run: `git diff -- src/template_novel_engine/skills/viral-story-remix/SKILL.md src/template_novel_engine/skill_assets.py src/template_novel_engine/cli.py src/template_novel_engine/remix_bundle.py tests/test_skill_assets.py tests/test_remix_bundle.py README.md`

Expected: only the planned JSON-only output changes appear.

- [ ] **Step 5: Commit the final verified state**

```bash
git add src/template_novel_engine/skills/viral-story-remix/SKILL.md src/template_novel_engine/skill_assets.py src/template_novel_engine/cli.py src/template_novel_engine/remix_bundle.py tests/test_skill_assets.py tests/test_remix_bundle.py README.md
git commit -m "feat: make remix skill output json only"
```

## Self-Review

- Spec coverage check: the plan covers JSON-only output contract, JSON-only file writing, raw JSON failure dumps, relaxed `human_readable_markdown` validation, CLI default path changes, tests, and README updates.
- Placeholder scan: no `TODO`, `TBD`, or unresolved references remain.
- Type consistency: the plan consistently uses `remix_bundle.json`, `.raw.json`, `validate_remix_bundle()`, and JSON-only prompt/validation logic.

# Template Novel Engine（重构版）

`AowrowAINovel` 现在的主入口是：

`viral-story-remix -> remix_bundle(.json/.md) -> generate -> 写作/审计/状态反射`

也就是说，`generate` 不再把 `爆款解析.md + 新故事思路.md` 当成推荐输入；推荐输入改为由 `viral-story-remix` 产出的 `remix_bundle.v1`。

## 1. 功能概览

1. `Remix Bundle`：加载并校验由 skill 产出的 `template_dna + story_bible + structure_map`
2. `T4` 非丢失上下文引擎（Context Engine）
3. `T5` 分章编排与写作（Plan/Compose/Write）
4. `T6` 状态反射与伏笔账本更新（State Reflection）
5. `T7` 审计与单轮自动修订（Audit/Reviser）
6. `T7 Batch` 批量审计（可选）
7. 反 AI 味策略链路（连接词密度/模板化表达检测与改写）
8. 内置章节分析（情绪弧线、冲突推进、角色状态变化等）
9. 保留 `T1/T2/T3` 作为手动调试工具链

## 2. 输出结构（v2）

默认输出目录：`outputs/<book_title>/`

```text
outputs/<book_title>/
  project/
    metadata.json
    template_dna.json
    story_bible.json
    structure_map.json
  world/
    world_rules.json
    conflicts.json
  characters/
    index.json
    char_*.json
  relationships/
    graph.json
  outlines/
    chapter_0001.json ...
  foreshadows/
    ledger.json
  chapters/
    0001/
      draft.md
      context.json
      contract.json
      analysis.json
      audit.json
      diff.md
      state_delta.json
      summary.json
    0002/
    ...
  runtime/
    state.json
    quality_history.json
  exports/
    第1章.txt
    第2章.txt
    全书.txt
  index/
    manifest.json
    t5_summary.json
```

`index/manifest.json` 用于索引当前书的章节进度和关键路径。

## 3. 项目结构

1. `main.py`：CLI 入口
2. `src/template_novel_engine/remix_bundle.py`：`remix_bundle.v1` 加载与校验
3. `src/template_novel_engine/context_engine.py`：T4
4. `src/template_novel_engine/chapter_orchestrator.py`：T5
5. `src/template_novel_engine/state_reflector.py`：T6
6. `src/template_novel_engine/audit_reviser.py`：T7
7. `src/template_novel_engine/asset_store.py`：v2 资产落盘与导出
8. `src/template_novel_engine/storage_layout.py`：v2 路径定义
9. `src/template_novel_engine/model_writer.py`：写作后端（builtin/openai/claude）
10. `src/template_novel_engine/template_parser.py` / `story_builder.py` / `structure_mapper.py`：保留给手动调试链使用
11. `src/template_novel_engine/app_config.py`：运行时配置加载

## 4. 快速开始（推荐）

### 4.1 准备 remix bundle

把 `viral-story-remix` 的产物保存成以下任一文件：

1. 项目根目录：`remix_bundle.json` 或 `remix_bundle.md`
2. `inputs/` 目录：`inputs/remix_bundle.json` 或 `inputs/remix_bundle.md`

推荐：

- 优先保存为 `inputs/remix_bundle.json`
- 如果保存的是 `.md`，文件中必须包含 `## Remix Bundle JSON` 区块和一个合法的 `json` fenced code block

### 4.1.1 在项目内使用内置 skill

项目已内置 `viral-story-remix`，可以直接查看或导出：

```powershell
python .\main.py skill list
python .\main.py skill show viral-story-remix
python .\main.py skill export viral-story-remix --out .\outputs\viral-story-remix.SKILL.md
```

也可以直接让项目内置 skill 生成 `remix_bundle.json`：

```powershell
python .\main.py skill scaffold viral-story-remix --viral-story .\inputs\viral_story.md --new-story-idea .\inputs\new_story_idea.md
```

如果已配置 `writer`，这个命令会直接调用模型，并默认写出：

- `inputs/remix_bundle.json`

随后执行：

```powershell
python .\main.py generate --count 20
```

### 4.2 准备配置

```powershell
Copy-Item .\template_novel_engine.config.example.json .\template_novel_engine.config.json
```

建议把真实模型密钥放环境变量或外部注入，不要把密钥写回仓库文件。

### 4.3 生成新书

```powershell
python .\main.py generate --count 20
```

如果输入文件不在默认位置，显式指定：

```powershell
python .\main.py generate --remix-bundle .\inputs\remix_bundle.json --count 20
```

也支持 Markdown bundle：

```powershell
python .\main.py generate --remix-bundle .\inputs\remix_bundle.md --count 20
```

常用参数：

1. `--remix-bundle`：指定 bundle 路径
2. `--chapter-start` / `--chapter-end`：章节区间
3. `--count`：从起始章节生成多少章（优先推荐）
4. `--writer-backend`：`builtin|openai|claude`
5. `--out-dir`：指定输出目录（默认 `outputs/<book_title>/`）

### 4.4 续写已有书

```powershell
python .\main.py continue --book "逆命者档案" --count 5
```

`--book` 可以是：

1. `outputs/` 下的书名目录名
2. 绝对路径目录

## 5. Remix Bundle 契约

推荐由 `viral-story-remix` 生成 `remix_bundle.v1`。

顶层字段：

```json
{
  "schema_version": "remix_bundle.v1",
  "project_brief": {},
  "source_trace": {},
  "template_dna": {},
  "story_bible": {},
  "structure_map": {},
  "human_readable_markdown": ""
}
```

当前引擎主路径真正消费的是：

- `template_dna`
- `story_bible`
- `structure_map`

关键约束：

- `schema_version` 必须是 `remix_bundle.v1`
- `structure_map.book_title == story_bible.metadata.title`
- `structure_map.target_chapters == story_bible.metadata.target_chapters`
- `human_readable_markdown` 必须与 companion markdown 同构

## 6. 使用真实模型写作

### 6.1 通过配置文件设置（推荐）

在 `template_novel_engine.config.json` 中设置：

```json
{
  "writer": {
    "backend": "openai",
    "model": "gpt-4.1-mini",
    "api_key": "YOUR_API_KEY",
    "base_url": "https://api.openai.com/v1",
    "temperature": 0.7,
    "max_tokens": 2200,
    "timeout_sec": 120
  }
}
```

然后执行：

```powershell
python .\main.py generate --count 5
```

### 6.2 命令行临时覆盖

```powershell
python .\main.py generate --count 3 --writer-backend openai --writer-model gpt-4.1-mini --writer-api-key "<KEY>"
```

## 7. 显式流水线（手动调试）

如果你要单独调试 `T1/T2/T3`，仍然可以使用旧链路，但它不再是主入口：

```powershell
python .\main.py t1 --template .\inputs\template_analysis.md --out .\outputs\<book_title>\project\template_dna.json
python .\main.py t2 --story-idea .\inputs\story_idea.md --out .\outputs\<book_title>\project\story_bible.json
python .\main.py t3 --template-dna .\outputs\<book_title>\project\template_dna.json --story-bible .\outputs\<book_title>\project\story_bible.json --out-map .\outputs\<book_title>\project\structure_map.json --out-outline .\outputs\<book_title>\project\volume_outline.md
python .\main.py t5 --template-dna .\outputs\<book_title>\project\template_dna.json --story-bible .\outputs\<book_title>\project\story_bible.json --structure-map .\outputs\<book_title>\project\structure_map.json --out-dir .\outputs\<book_title>\process
```

说明：

1. `generate/continue` 是推荐生产入口。
2. `t1/t2/t3` 更适合调试旧解析逻辑或做对照试验。

## 8. 常用命令总览

```powershell
python .\main.py --help
python .\main.py generate --help
python .\main.py continue --help
python .\main.py t5 --help
```

命令说明：

1. `generate`：新建并生成书，主输入为 remix bundle
2. `continue`：在现有书上续写
3. `t1/t2/t3/t4/t5/t6/t7/t7-batch`：分阶段执行
4. `run-all`：旧链路，仅执行 T1+T2+T3

## 9. 配置文件说明

配置优先级（高到低）：

1. CLI 参数
2. `template_novel_engine.config.json`
3. 内置默认值

关键字段：

1. `defaults`：默认章节范围、token 预算、是否自动跑 T7 Batch
2. `length_control`：字数目标和容差控制
3. `runtime_prompt_view`：运行时提示视图裁剪
4. `storage.layout_version`：当前为 `v2`
5. `storage.write_debug_package`：是否写出 `chapters/<chapter>/package.json`
6. `storage.write_alignment_file`：是否写出 `chapters/<chapter>/alignment.json`
7. `storage.export_plain_text`：是否写出 `exports/第N章.txt`
8. `storage.export_full_book`：是否写出 `exports/全书.txt`
9. `analysis`：章节分析开关
10. `anti_ai_style`：反 AI 味规则
11. `writer`：模型后端参数

## 10. 注意事项

1. 本项目当前无需第三方依赖（`requirements.txt` 为空依赖）。
2. `builtin` 写作后端用于本地演示和冒烟测试；真实创作建议接入 `openai` 或 `claude`。
3. 输出目录按书名自动创建；若书名含非法文件名字符，会自动清洗。
4. 推荐把 `viral-story-remix` 的输出保存为 `inputs/remix_bundle.json`，这样 `generate` 可以零参数启动。

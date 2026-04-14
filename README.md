# Template Novel Engine（重构版）

基于《爆款模板驱动小说系统方案》，实现并串联 T1~T7 全流程。

本次重构后，输出目录采用领域化 `v2` 结构，按项目资产、角色档案、人物关系、章节包、运行时状态分层存放，不再使用旧的 `关键资产/正文/过程` 结构。

## 1. 功能概览

1. `T1` 模板解析（Template Parser）
2. `T2` 故事圣经构建（Story Builder）
3. `T3` 结构映射（Structure Mapper）
4. `T4` 非丢失上下文引擎（Context Engine）
5. `T5` 分章编排与写作（Plan/Compose/Write）
6. `T6` 状态反射与伏笔账本更新（State Reflection）
7. `T7` 审计与单轮自动修订（Audit/Reviser）
8. `T7 Batch` 批量审计（可选）
9. 反 AI 味策略链路（连接词密度/模板化表达检测与改写）
10. 内置章节分析（情绪弧线、冲突推进、角色状态变化等）

## 2. 重构后的输出结构（v2）

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

默认情况下不会写出 `chapters/<chapter>/package.json` 与 `chapters/<chapter>/alignment.json`，纯文本导出也默认关闭；这些产物现在由 `storage` 配置显式控制。

## 3. 项目结构

1. `main.py`：CLI 入口
2. `src/template_novel_engine/template_parser.py`：T1
3. `src/template_novel_engine/story_builder.py`：T2
4. `src/template_novel_engine/structure_mapper.py`：T3
5. `src/template_novel_engine/context_engine.py`：T4
6. `src/template_novel_engine/chapter_orchestrator.py`：T5
7. `src/template_novel_engine/state_reflector.py`：T6
8. `src/template_novel_engine/audit_reviser.py`：T7
9. `src/template_novel_engine/asset_store.py`：v2 资产落盘与导出
10. `src/template_novel_engine/storage_layout.py`：v2 路径定义
11. `src/template_novel_engine/asset_indexer.py`：manifest 索引维护
12. `src/template_novel_engine/anti_ai_style.py`：反 AI 味规则与改写
13. `src/template_novel_engine/chapter_analyzer.py`：章节分析
14. `src/template_novel_engine/model_writer.py`：写作后端（builtin/openai/claude）
15. `src/template_novel_engine/app_config.py`：运行时配置加载

## 4. 快速开始（推荐）

### 4.1 准备输入

在以下任一位置放置输入文件即可：

1. 项目根目录：`爆款解析.md`、`新故事思路.md`
2. 或 `inputs/` 目录：`inputs/爆款解析.md`、`inputs/新故事思路.md`

也支持兼容命名：`template_analysis.md`、`story_idea.md`（根目录或 `inputs/` 下）。

### 4.2 准备配置

```powershell
Copy-Item .\template_novel_engine.config.example.json .\template_novel_engine.config.json
```

### 4.3 生成新书

```powershell
python .\main.py generate --count 20
```

常用参数：

1. `--chapter-start` / `--chapter-end`：章节区间
2. `--count`：从起始章节生成多少章（优先推荐）
3. `--writer-backend`：`builtin|openai|claude`
4. `--out-dir`：指定输出目录（默认 `outputs/<book_title>/`）

示例：

```powershell
python .\main.py generate --chapter-start 1 --count 10 --writer-backend builtin
```

### 4.4 续写已有书

```powershell
python .\main.py continue --book "逆命者档案" --count 5
```

`--book` 可以是：

1. `outputs/` 下的书名目录名
2. 绝对路径目录

## 5. 使用真实模型写作

### 5.1 通过配置文件设置（推荐）

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

然后直接执行：

```powershell
python .\main.py generate --count 5
```

### 5.2 命令行临时覆盖

```powershell
python .\main.py generate --count 3 --writer-backend openai --writer-model gpt-4.1-mini --writer-api-key "<KEY>"
```

## 6. 显式流水线（手动控制）

适合调试每个阶段产物。

```powershell
python .\main.py t1 --template .\inputs\template_analysis.md --out .\outputs\<book_title>\project\template_dna.json
python .\main.py t2 --story-idea .\inputs\story_idea.md --out .\outputs\<book_title>\project\story_bible.json
python .\main.py t3 --template-dna .\outputs\<book_title>\project\template_dna.json --story-bible .\outputs\<book_title>\project\story_bible.json --out-map .\outputs\<book_title>\project\structure_map.json --out-outline .\outputs\<book_title>\project\volume_outline.md
python .\main.py t5 --template-dna .\outputs\<book_title>\project\template_dna.json --story-bible .\outputs\<book_title>\project\story_bible.json --structure-map .\outputs\<book_title>\project\structure_map.json --out-dir .\outputs\<book_title>\process
```

说明：

1. `t5 --out-dir` 下主要是过程产物（如 `chapter_package_chXX.json`）。
2. 日常生产建议使用 `generate/continue`，由系统自动写入 `v2` 领域化目录并维护 `manifest`。

## 7. 常用命令总览

```powershell
python .\main.py --help
python .\main.py generate --help
python .\main.py continue --help
python .\main.py t5 --help
```

命令说明：

1. `generate`：新建并生成书（自动执行 T1+T2+T3+T5）
2. `continue`：在现有书上续写（跳过 T1+T2+T3）
3. `t1/t2/t3/t4/t5/t6/t7/t7-batch`：分阶段执行
4. `run-all`：仅执行 T1+T2+T3

## 8. 配置文件说明

配置优先级（高到低）：

1. CLI 参数
2. `template_novel_engine.config.json`
3. 内置默认值

示例配置见：`template_novel_engine.config.example.json`

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
10. `anti_ai_style`：反 AI 味规则（禁用连接词套话、开头重复等）
11. `writer`：模型后端参数

`storage` 示例：

```json
{
  "storage": {
    "layout_version": "v2",
    "write_debug_package": false,
    "write_alignment_file": false,
    "export_plain_text": false,
    "export_full_book": false
  }
}
```

## 9. 反 AI 味与情感化相关产物

重构后相关数据落盘位置：

1. `chapters/<chapter>/analysis.json`：章节分析（冲突、情绪弧线、角色状态等）
2. `chapters/<chapter>/audit.json`：T7 审计结果
3. `chapters/<chapter>/diff.md`：自动修订差异
4. `runtime/state.json`：跨章节状态累计
5. `runtime/quality_history.json`：逐章质量历史（是否通过、硬失败数、警告数）
6. `foreshadows/ledger.json`：伏笔台账

## 10. 注意事项

1. 本项目当前无需第三方依赖（`requirements.txt` 为空依赖）。
2. `builtin` 写作后端用于本地演示和冒烟测试；真实创作建议接入 `openai` 或 `claude`。
3. 输出目录按书名自动创建；若书名含非法文件名字符，会自动清洗。

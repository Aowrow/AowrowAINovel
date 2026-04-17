---
name: viral-story-remix
description: Use when given one爆款故事 and one新故事思路 and the result must be a stable remix bundle that is directly consumable by AowrowAINovel.
---

# Viral Story Remix

## Active Spec

下面这份规范是当前唯一有效规范。

- 忽略任何旧版输出习惯。
- 不允许自由发挥输出格式。
- 不允许省略 machine-readable 结果。
- 不允许外泄完整中间推理链。

目标：把一份爆款故事和一份新故事思路，转换成一个稳定、可解析、可直接输入 `AowrowAINovel generate` 的 `remix_bundle.v1`，并同时给出严格对齐的人类可读大纲。

## Inputs

必填输入：

- `viral_story`
  - 爆款故事原文，或至少足以暴露完整爆点机制的完整材料。
- `new_story_idea`
  - 新故事种子，可是一句话、简介或完整文本。

可选输入：

- `genre_direction`
- `audience_direction`
- `emotion_intensity`
- `episode_count`
- `target_length`
- `must_keep`
- `forbidden`

默认规则：

- 如果用户没给 `episode_count`，默认按 20 到 40 集自适应。
- 女频都市、重生、复仇、豪门逆袭、强情绪对抗题材，优先 28 到 36 集。
- 如果用户素材很短，也必须先保留核心设定，再做补强，不允许直接改成通用模板。

## Output Contract

最终输出只能是一个合法 JSON 对象。

不允许在 JSON 前后加解释、寒暄、免责声明、提示词说明、Markdown 标题、代码围栏。

### Final JSON Payload

硬规则：

- 必须是合法 JSON。
- 只能使用双引号。
- 不允许注释。
- 不允许 trailing commas。
- 不允许 `...`、`TODO`、`TBD`、`待补`、占位字段。
- `schema_version` 必须固定为 `"remix_bundle.v1"`。

顶层字段固定为：

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

#### `project_brief`

必须包含：

- `title`
- `genre`
- `tone`
- `episode_count`
- `target_length`
- `must_keep`
- `forbidden`
- `core_hook`
- `core_payoff`

约束：

- `episode_count` 必须是正整数。
- `must_keep` / `forbidden` 必须是字符串数组。

#### `source_trace`

必须包含：

- `viral_story_title`
- `new_story_title`
- `migration_focus`
- `retained_elements`

约束：

- `retained_elements` 必须是字符串数组。
- `migration_focus` 必须描述迁移的机制，不允许写成换皮复刻。

#### `template_dna`

这是抽象后的爆款机制模板，不是原故事复述。

必须包含：

- `schema_version`
- `source_file`
- `core_premise`
- `template_formulas`
- `narrative_stages`
- `rhythm_beats`
- `dialogue_patterns`
- `principles`
- `reusable_motifs`

要求：

- `schema_version` 固定为 `"v1"`。
- `source_file` 固定写 `"skill://viral-story-remix"`。
- `core_premise` 只能描述机制，不允许带原作专有名词。
- `narrative_stages` 至少 4 段。
- `rhythm_beats` 必须覆盖完整章节范围。
- `principles` 至少包含：
  - 主角主体性不能丢
  - 兑现点必须分阶段出现
  - 不能提前消耗终局高潮

#### `story_bible`

这是小说项目直接消费的故事圣经。

必须包含：

- `schema_version`
- `source_file`
- `metadata`
- `premise`
- `world`
- `characters`
- `factions`
- `conflicts`
- `constraints`

其中：

- `schema_version` 固定为 `"v1"`
- `source_file` 固定写 `"skill://viral-story-remix"`

`metadata` 必须包含：

- `title`
- `genre`
- `tone`
- `protagonist_name`
- `target_chapters`
- `chapter_word_target`

`premise` 必须包含：

- `logline`
- `theme`
- `selling_points`

`world` 必须包含：

- `era`
- `locations`
- `rules`
- `power_system`

`characters` 至少包含 3 人：

- 主角
- 主要对手
- 关键护道者或关键盟友

每个角色至少包含：

- `name`
- `role`
- `goal`
- `flaw`
- `arc`

`conflicts` 必须包含：

- `main_conflict`
- `secondary_conflicts`

`constraints` 必须包含：

- `must_have`
- `must_avoid`

#### `structure_map`

这是 `AowrowAINovel` 内部真正使用的仿写大纲契约。

必须包含：

- `schema_version`
- `book_title`
- `target_chapters`
- `stage_contracts`
- `chapter_plan`

要求：

- `schema_version` 固定为 `"v1"`
- `book_title` 必须等于 `story_bible.metadata.title`
- `target_chapters` 必须等于 `story_bible.metadata.target_chapters`

`stage_contracts` 规则：

- 至少 4 段
- 必须连续覆盖 `1..target_chapters`
- 不允许断档
- 不允许重叠

每个 `stage_contract` 必须包含：

- `stage_id`
- `template_title`
- `chapter_start`
- `chapter_end`
- `story_goal`
- `must_keep`
- `escalation_target`
- `pov_focus`
- `setpiece_candidates`

`chapter_plan` 规则：

- 必须从第 1 章连续写到第 `target_chapters` 章
- 每章必须一条
- 不允许缺章
- 不允许重复章号

每个 `chapter_plan` item 必须包含：

- `chapter`
- `title`
- `stage_id`
- `objective`

`objective` 要求：

- 必须是具体可执行的章节任务。
- 不能只写“推进剧情”。
- 不能只写抽象标签。
- 必须和所在 `stage_contract` 对齐。

#### `human_readable_markdown`

必须是字符串字段。

允许为空字符串：

```json
"human_readable_markdown": ""
```

如果填写内容，也只能是简短的人类可读摘要；不再要求 companion markdown 镜像结构。

## Migration Principles

迁移的是机制，不是表皮。

必须优先迁移：

- 钩子设计
- 旧认知被推翻的方式
- 冤屈与补偿结构
- 护道者功能
- 主角夺回主体性的节点
- 阶梯式升级路径
- 从个人冲突扩大到系统冲突的过程
- 最终价值立场

必须避免：

- 只换名字不换结构来源
- 直接照搬原作世界观名词
- 原事件顺序原样复制
- 原名台词轻改后继续使用
- 把新故事写成失去个性的通用复仇模板

## Self Check

输出前必须逐项确认：

- JSON 合法可解析。
- 最终输出只有一个合法 JSON 对象，没有 markdown 包装。
- `schema_version == "remix_bundle.v1"`。
- `book_title == story_bible.metadata.title`。
- `target_chapters == episode_count == structure_map.target_chapters == story_bible.metadata.target_chapters`。
- `stage_contracts` 连续覆盖全书。
- `chapter_plan` 从 1 到结尾无缺章。
- 主角主体性没有被护道者抢走。
- 结果是新故事，不是爆款故事换皮。
- `human_readable_markdown` 是字符串；可为空。
- 没有泄露完整中间分析。
- 没有出现占位词、注释式 JSON、散文式分集提纲。

## Quick Rules

- 两份输入齐全才正式执行。
- 输出必须直接给 JSON 对象。
- JSON 必须能直接喂给 `AowrowAINovel generate`。
- 默认产出完整 bundle，不接受“只写一个文本大纲就结束”。
- 如果用户要求更短，只能压缩说明文字，不能删掉 bundle 必需字段。
- 如果资料不足，可以合理补全，但必须保留用户核心设定。

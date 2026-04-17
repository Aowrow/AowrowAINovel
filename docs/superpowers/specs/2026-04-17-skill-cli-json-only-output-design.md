## Overview

Refine the built-in `viral-story-remix` execution flow so it produces only a machine-consumable `remix_bundle.v1` JSON file. Remove the companion markdown requirement from the skill contract, stop validating or saving markdown output, and make `skill scaffold` default to `inputs/remix_bundle.json`.

This change keeps the downstream novel engine unchanged because `generate` already supports reading a pure JSON remix bundle.

## Problem Statement

The current direct-execution flow asks the model to return both JSON and companion markdown in one response. That adds token overhead, increases truncation risk, and creates output the user does not need. The user only wants the JSON bundle used by the engine and does not want the markdown section generated or saved.

## Goals

- Change the built-in skill contract to require only a valid `remix_bundle.v1` JSON object.
- Make `skill scaffold` default to `inputs/remix_bundle.json`.
- Validate only the JSON bundle payload.
- Remove markdown-specific prompt instructions and validation from the direct execution path.
- Preserve `generate` compatibility without changing its main behavior.

## Non-Goals

- Do not redesign the remix bundle schema itself.
- Do not add a second output artifact for human-readable markdown.
- Do not broaden the command surface.
- Do not change the `generate` pipeline beyond continuing to consume the bundle.

## Recommended Approach

Adopt a JSON-only contract end-to-end:

1. Update `SKILL.md` so the final output must be one valid JSON object.
2. Update `skill_assets.py` to request only JSON, validate only JSON, and write `remix_bundle.json`.
3. Update `cli.py` so `skill scaffold` defaults to `inputs/remix_bundle.json`.

This is the smallest and cleanest approach because the downstream loader already supports pure JSON files.

## Why This Works

`src/template_novel_engine/remix_bundle.py` already supports:

- pure JSON documents starting with `{`
- markdown documents containing a fenced JSON block

That means the engine does not depend on the markdown wrapper. Markdown is optional for humans, not required for the program.

## Architecture Changes

### Skill Contract

Change the output contract in:

`src/template_novel_engine/skills/viral-story-remix/SKILL.md`

From:

- `## Remix Bundle JSON`
- `## Companion Markdown`

To:

- final output must be one valid JSON object
- no surrounding explanation
- no markdown wrapper

Also remove `human_readable_markdown` / companion markdown requirements from the skill text unless the engine schema still requires a string field. If the schema continues to require `human_readable_markdown`, keep the field in JSON but allow it to be a minimal concise string rather than a mirrored markdown document.

### Direct Execution Path

Update `src/template_novel_engine/skill_assets.py` so it:

- builds a JSON-only execution prompt
- validates the raw response as JSON
- passes the decoded payload into remix bundle validation
- writes `remix_bundle.json`

The raw failure dump can remain for debugging, but the primary success output becomes JSON only.

### CLI Defaults

Update `src/template_novel_engine/cli.py`:

- `skill scaffold --out` default becomes `<project-root>/inputs/remix_bundle.json`
- help text reflects JSON output

## Validation Strategy

Success path:

1. model returns raw text
2. raw text must decode as JSON object
3. decoded payload passes `validate_remix_bundle()`
4. write `inputs/remix_bundle.json`

Failure path:

- invalid JSON: fail with clear message
- valid JSON but invalid schema: fail with clear message
- optional raw dump remains available for diagnosis

## Testing Strategy

Update `tests/test_skill_assets.py` to cover:

- parser default output path is `inputs/remix_bundle.json`
- successful execution writes JSON file
- invalid JSON output is rejected
- invalid schema output is rejected
- builtin backend still rejected

Keep `tests/test_remix_bundle.py` green to confirm the loader still accepts pure JSON bundles.

## README Changes

Update examples to:

```powershell
python .\main.py skill scaffold viral-story-remix --viral-story .\inputs\viral_story.md --new-story-idea .\inputs\new_story_idea.md
python .\main.py generate --count 20
```

Document that the first command now directly creates:

- `inputs/remix_bundle.json`

## Implementation Boundaries

- Keep changes minimal and localized.
- Prefer using existing remix bundle validation instead of creating a second validator.
- Do not reintroduce markdown output unless explicitly requested later.

## Open Questions Resolved

- The user wants JSON only, not mixed JSON+markdown output.
- The skill contract should be updated accordingly.
- The downstream engine can already consume JSON directly, so no loader redesign is needed.

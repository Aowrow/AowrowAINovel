## Overview

Integrate `viral-story-remix` into `AowrowAINovel` as a project-owned skill asset that can be used directly from the existing CLI. The integration keeps the current `generate` pipeline unchanged: `generate` continues to consume a `remix_bundle.v1`, while the new CLI surface makes the skill available inside the project for viewing, exporting, and building a model-ready execution package.

The goal is to let users work entirely inside the project when preparing novel-writing inputs, without re-implementing the skill contract as Python generation logic.

## Goals

- Vendor `D:\codexright\skill-drafts\viral-story-remix\SKILL.md` into the project as a maintained asset.
- Add CLI commands that expose the skill from within `AowrowAINovel`.
- Allow users to scaffold a prompt package from local source materials so an external model can generate a valid `remix_bundle`.
- Preserve the current `remix_bundle -> generate` workflow and schema contract.

## Non-Goals

- Do not convert the `viral-story-remix` writing contract into a Python content generator.
- Do not change `remix_bundle.v1` validation rules.
- Do not change the behavior of `generate`, `continue`, or the T1-T7 pipeline.
- Do not add third-party dependencies.

## Recommended Approach

Use a project-owned skill asset plus a thin asset-management layer in the CLI.

This is preferred over embedding the skill logic into Python because:

- The current engine already treats `remix_bundle` as the stable machine-readable contract.
- The skill is best maintained as a text specification asset rather than duplicated as code rules.
- Future edits to the skill can remain localized to the vendored `SKILL.md` and its packaging helpers.

## Alternatives Considered

### 1. Project-owned skill asset plus CLI accessors

Add the skill file to the repository, expose it via CLI, and scaffold model-ready prompt packages.

Pros:

- Minimal change to the existing architecture.
- Keeps responsibilities clear: CLI manages assets, model produces bundle, engine consumes bundle.
- Easy to maintain when the skill evolves.

Cons:

- Still requires an external model or agent step to produce the final `remix_bundle`.

### 2. Project-owned skill asset plus richer prompt packager

Same as option 1, but with more packaging features, templates, or profile presets.

Pros:

- Slightly more ergonomic for repeated use.

Cons:

- More surface area without changing the core workflow.
- Not necessary for the current requirement.

### 3. Re-implement skill contract in Python

Encode `viral-story-remix` output requirements directly in engine code.

Pros:

- Reduces dependence on an external model step.

Cons:

- High implementation and maintenance cost.
- Duplicates a text-first spec as code.
- Harder to evolve without schema drift and behavior mismatch.

## Architecture

### Skill Asset Location

Vendor the draft skill into:

`src/template_novel_engine/skills/viral-story-remix/SKILL.md`

This becomes the only in-project source of truth for the skill content.

### Asset Management Module

Add a small module:

`src/template_novel_engine/skill_assets.py`

Responsibilities:

- Enumerate available built-in skills.
- Resolve a skill name to its file path.
- Read a skill file as text.
- Export a skill to an arbitrary output path.
- Build a scaffolded execution package from the skill plus user-supplied input materials.

Non-responsibilities:

- No LLM invocation.
- No bundle generation.
- No remix contract interpretation beyond packaging.

### CLI Surface

Add a new top-level command group:

`python main.py skill ...`

Subcommands:

1. `skill list`
2. `skill show <name>`
3. `skill export <name> --out <path>`
4. `skill scaffold viral-story-remix --viral-story <path> --new-story-idea <path> --out <path>`

The `skill` command group is intentionally narrow and file-oriented.

## Command Design

### `skill list`

Purpose:

- Show all built-in skills currently available in the project.

Expected initial output:

- `viral-story-remix`

### `skill show viral-story-remix`

Purpose:

- Print the vendored `SKILL.md` content to stdout.

Usage:

- Quick inspection of the active contract without leaving the project.

### `skill export viral-story-remix --out <path>`

Purpose:

- Copy the vendored skill to a user-specified path.

Usage:

- Feed the skill into an external agent, chat model, or workflow tool.

Behavior:

- Ensure parent directories exist before writing.
- Write UTF-8 text exactly as stored in the project.

### `skill scaffold viral-story-remix --viral-story <path> --new-story-idea <path> --out <path>`

Purpose:

- Create a model-ready markdown execution package that contains the active skill and the two required inputs.

Required inputs:

- `--viral-story`
- `--new-story-idea`
- `--out`

Behavior:

- Read both input files as UTF-8 text.
- Read the vendored skill content.
- Write a single markdown package that tells the model to strictly follow the skill and emit only the contract-defined output.

## Scaffold Output Format

The scaffold command writes a markdown file with fixed sections:

```md
# Skill Execution Package

## Skill Name
viral-story-remix

## Execution Instruction
Strictly follow the SKILL.md below. The final output must contain only:
1. `## Remix Bundle JSON`
2. `## Companion Markdown`

## SKILL.md
...vendored skill content...

## Input: viral_story
...source text...

## Input: new_story_idea
...source text...
```

This file is intended to be passed to an external model. The model output can then be saved as `inputs/remix_bundle.md` or `inputs/remix_bundle.json` and consumed by the existing engine.

## Data Flow

1. User prepares `viral_story` and `new_story_idea` files.
2. User runs `python main.py skill scaffold viral-story-remix ...`.
3. CLI produces a markdown execution package using the vendored skill plus the two inputs.
4. User submits that package to an external model or agent.
5. Model returns `## Remix Bundle JSON` and `## Companion Markdown`.
6. User saves the result as `inputs/remix_bundle.md` or `inputs/remix_bundle.json`.
7. User runs `python main.py generate --remix-bundle ...` or relies on the default bundle discovery path.

## Error Handling

The new CLI path should fail fast with explicit file-oriented errors:

- Unknown skill name: raise a clear `ValueError` listing available skills.
- Missing input file: raise `FileNotFoundError` with the missing path.
- Empty input file: reject with a clear `ValueError`.
- Unwritable output path: allow the existing top-level CLI error guard to surface the exception message.

The CLI should not attempt to validate generated `remix_bundle` content during scaffold generation because that content does not exist yet.

## Testing Strategy

Add focused tests around the new skill asset layer and CLI wiring.

### New tests

File: `tests/test_skill_assets.py`

Cover:

- Listing built-in skills includes `viral-story-remix`.
- Reading `viral-story-remix` returns the vendored content.
- Export writes the exact skill text to disk.
- Scaffold writes a markdown package that contains:
  - the expected header,
  - the skill name,
  - the vendored skill body,
  - the `viral_story` input,
  - the `new_story_idea` input.

### Regression coverage

Keep the current `tests/test_remix_bundle.py` coverage intact to ensure `generate` remains bundle-driven and unchanged.

Optionally add one small parser/CLI assertion if needed to confirm the `skill` command group does not interfere with `generate` behavior.

## README Changes

Document the in-project skill workflow:

1. `python .\main.py skill show viral-story-remix`
2. `python .\main.py skill scaffold viral-story-remix --viral-story ... --new-story-idea ... --out ...`
3. Send the scaffolded package to a model and save the result as `inputs/remix_bundle.md` or `.json`
4. `python .\main.py generate --remix-bundle ...`

This keeps the README aligned with the engine's current recommended workflow.

## Implementation Boundaries

- Keep changes minimal and localized.
- Avoid introducing new abstractions beyond one small asset helper module.
- Do not rewrite existing remix bundle loading logic.
- Do not broaden the command scope beyond built-in skill management and scaffolding.

## Open Questions Resolved

- Integration style: use built-in skill files rather than a Python implementation of the skill.
- Main workflow: scaffold prompt package inside the project, then let the existing `generate` consume the resulting `remix_bundle`.
- Scope: ship the minimal built-in skill workflow now; richer packaging or profile presets can wait.

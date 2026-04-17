## Overview

Correct the previously added `skill scaffold` behavior so it directly executes the built-in `viral-story-remix` skill through the project's configured LLM writer and produces a valid `remix_bundle` result file. The command should no longer stop at generating a prompt package unless that is explicitly requested as a debug artifact.

The intended user flow is:

1. Prepare `inputs/viral_story.md`
2. Prepare `inputs/new_story_idea.md`
3. Run `python .\main.py skill scaffold viral-story-remix --viral-story ... --new-story-idea ...`
4. Receive `inputs/remix_bundle.md`
5. Run `python .\main.py generate --count ...`

## Problem Statement

The current implementation of `skill scaffold` only writes a markdown prompt package. That behavior does not match the user's intended workflow, because no new story bundle is produced inside the project after running the command. The root mismatch is that the command name was treated as "assemble prompt scaffolding" while the user expected "execute the skill and return the generated writing artifact."

## Goals

- Make `skill scaffold` directly call a real configured model.
- Default the result file to `inputs/remix_bundle.md`.
- Reuse the project's existing writer configuration and CLI writer overrides.
- Validate the model response with the existing `load_remix_bundle()` contract before declaring success.
- Keep `generate` unchanged and continue using the resulting `remix_bundle` file.

## Non-Goals

- Do not add a separate long-running orchestration system.
- Do not introduce a second user-facing command unless necessary.
- Do not change the `remix_bundle.v1` schema.
- Do not add third-party dependencies.
- Do not rewrite chapter-generation prompt infrastructure unless needed for a small reusable LLM text entry point.

## Recommended Approach

Upgrade `skill scaffold` from a file packager into a direct execution command that:

1. builds a prompt from the built-in skill plus source materials,
2. sends that prompt to the configured LLM backend,
3. validates the returned markdown as a valid remix bundle,
4. writes the final result to `inputs/remix_bundle.md` by default.

This is preferred over adding a new `skill run` command because the user explicitly wants the existing command to produce the bundle directly, and the current command has not yet become an established stable interface.

## Alternatives Considered

### 1. Change `skill scaffold` to execute directly

Pros:

- Matches user expectation exactly.
- Smallest change to the user workflow.
- Keeps one obvious entry point.

Cons:

- Changes semantics from "scaffold" toward "run and emit result".

### 2. Keep `skill scaffold`, add `skill run`

Pros:

- Preserves the original prompt-only meaning.
- Cleaner separation between prompt packaging and execution.

Cons:

- Does not match the user's requested behavior for the existing command.
- Adds extra command surface and more explanation burden.

### 3. Emit both prompt package and final result by default

Pros:

- Convenient for debugging.

Cons:

- More output files and more moving parts.
- Unnecessary for the current need.

## Command Behavior

### `skill scaffold viral-story-remix`

New behavior:

- Reads built-in `SKILL.md`
- Reads `--viral-story`
- Reads `--new-story-idea`
- Builds a single execution prompt
- Calls the configured LLM backend
- Validates the returned text as a remix bundle markdown document
- Writes the final result to `--out` or defaults to `inputs/remix_bundle.md`

The command should print a success line only after validation succeeds.

### Default output path

If `--out` is omitted, default to:

`<project-root>/inputs/remix_bundle.md`

This keeps the output aligned with the engine's existing bundle discovery path.

### Optional debug artifact

Optionally support a debug raw-response file such as:

`inputs/remix_bundle.raw.md`

This should only be used when model output fails validation or when an explicit debug flag is added later. It is not required as a primary success artifact.

## Writer Integration

Reuse the existing `writer` config from:

- `template_novel_engine.config.json`
- current CLI writer override patterns already used by `generate` and `continue`

Required constraints:

- `skill scaffold` must reject `builtin`
- backend must be `openai` or `claude`
- model and API key must already satisfy `normalize_writer_config()` requirements

This keeps writer configuration consistent across the project.

## Architecture

### `skill_assets.py`

Evolve this module from prompt-only packaging into direct skill execution support.

Responsibilities:

- Build the skill execution prompt from built-in skill text and two required inputs
- Invoke a reusable generic LLM text-generation function
- Validate returned markdown via `load_remix_bundle()`
- Write the validated result file

### `model_writer.py`

Add a small generic text-generation entry point that reuses the existing backend request paths but is not tied to chapter-writing prompt structures.

Candidate shape:

- accept `writer_config`
- accept `system_prompt`
- accept `user_prompt`
- return raw text plus lightweight metadata

This should be implemented as a minimal shared wrapper over the existing backend call path, not a second parallel HTTP stack.

### `cli.py`

Update the `skill scaffold` parser and execution path to:

- accept writer overrides like other model-backed commands
- default `--out` to `inputs/remix_bundle.md`
- call the new direct execution function rather than prompt-only file assembly

## Prompt Construction

The prompt should contain:

- a short execution instruction that explicitly requires only:
  - `## Remix Bundle JSON`
  - `## Companion Markdown`
- the built-in `SKILL.md`
- `viral_story`
- `new_story_idea`

The system prompt should be minimal and strict, because the detailed contract already lives in `SKILL.md`.

## Validation Flow

After model output is received:

1. Ensure the text contains `## Remix Bundle JSON`
2. Ensure the text contains `## Companion Markdown`
3. Write or stage text for validation input
4. Call existing `load_remix_bundle()` against the markdown result
5. Only on success write the final `remix_bundle.md` result path

If validation fails, the command should raise a clear error such as:

`LLM output is not a valid remix bundle`

## Error Handling

### Configuration errors

Examples:

- backend is `builtin`
- missing model
- missing API key

Behavior:

- fail fast with a clear message explaining that `skill scaffold` requires `openai` or `claude`

### LLM request errors

Examples:

- HTTP failure
- timeout
- provider error response

Behavior:

- surface the existing writer-layer error with a small command-context prefix if needed

### Output contract errors

Examples:

- model returns chatty prose
- malformed JSON block
- missing required top-level sections

Behavior:

- do not treat the run as successful
- optionally preserve raw response for debugging
- report that the output failed remix bundle validation

## Testing Strategy

### Update skill tests

`tests/test_skill_assets.py` should shift from prompt-only expectations to direct execution behavior.

Cover:

- default output path behavior
- rejection of `builtin` backend
- successful execution path using a stubbed generic LLM text generator
- validation failure path for malformed model output

### Regression safety

Keep existing `tests/test_remix_bundle.py` coverage intact so `generate` remains bundle-driven and unchanged.

## README Changes

Update the skill workflow to reflect direct execution:

```powershell
python .\main.py skill scaffold viral-story-remix --viral-story .\inputs\viral_story.md --new-story-idea .\inputs\new_story_idea.md
python .\main.py generate --count 20
```

Documentation should explain that the first command now directly creates `inputs/remix_bundle.md` using the configured LLM writer.

## Implementation Boundaries

- Keep the direct-execution path minimal.
- Avoid introducing new command groups.
- Reuse existing writer config and backend plumbing.
- Keep `generate` unchanged.

## Open Questions Resolved

- Existing command should be corrected rather than replaced.
- Default success artifact should be `remix_bundle.md`.
- Writer configuration should be shared with the rest of the engine.

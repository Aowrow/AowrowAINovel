from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from template_novel_engine.context_engine import compose_context


class ComposeContextArtifactRegressionTests(unittest.TestCase):
    def test_compose_context_uses_previous_chapter_artifacts_when_book_root_present(self) -> None:
        template_dna = {
            "principles": [],
            "dialogue_patterns": [],
        }
        story_bible = {
            "metadata": {"title": "Artifact Recall"},
            "world": {"rules": ["Magic demands a memory toll."]},
            "characters": [{"name": "Mira"}],
            "conflicts": {"main_conflict": "Mira must cross the haunted archive."},
        }
        structure_map = {
            "target_chapters": 6,
            "stage_contracts": [
                {
                    "stage_id": "stage_01",
                    "template_title": "Opening",
                    "chapter_start": 1,
                    "chapter_end": 3,
                    "story_goal": "Escalate the archive crossing.",
                    "must_keep": [],
                    "escalation_target": "Raise pressure.",
                },
            ],
            "chapter_plan": [
                {"chapter": 1, "objective": "Mira enters the archive."},
                {"chapter": 2, "objective": "Mira finds the missing ledger."},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            book_root = Path(temp_dir)
            chapter_dir = book_root / "chapters" / "0001"
            chapter_dir.mkdir(parents=True, exist_ok=True)
            (chapter_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "chapter": 1,
                        "summary": "Mira bargains with the archive ghosts and learns the ledger answers to blood.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (chapter_dir / "draft.md").write_text(
                "# Chapter 1\n\nEarlier beats.\n\nThe ghostly ledger snapped shut as Mira pressed her palm to the cover.\n",
                encoding="utf-8",
            )

            runtime_state = {
                "book_root": str(book_root),
                "character_states": [
                    {
                        "name": "Mira",
                        "status": "active",
                        "survival_status": "active",
                        "current_state": "binding herself to the archive",
                        "position": "archive vault",
                        "last_updated_chapter": 1,
                    },
                ],
                "irreversible_events": [],
                "active_threads": [
                    {
                        "thread_id": "main_conflict",
                        "title": "Mira must cross the haunted archive.",
                        "status": "active",
                        "priority": "P0",
                        "introduced_chapter": 1,
                        "last_updated_chapter": 1,
                        "due_chapter": 3,
                    },
                ],
                "thread_ledger": [],
                "chapter_summaries": [],
                "foreshadows": [],
                "foreshadow_ledger": [],
                "state_deltas": [],
                "author_intent": "Keep the ghost bargain consequences visible.",
                "current_focus": "Mira studies the ledger.",
                "runtime_prompt_view": {},
            }

            bundle, _, runtime = compose_context(
                template_dna=template_dna,
                story_bible=story_bible,
                structure_map=structure_map,
                runtime_state=runtime_state,
                chapter_no=2,
            )

        tier3_items = bundle["tiers"]["tier_3_retrieval_evidence"]["items"]
        tier3_text = "\n".join(item["text"] for item in tier3_items)

        self.assertIn(
            "Mira bargains with the archive ghosts and learns the ledger answers to blood.",
            tier3_text,
        )
        self.assertIn(
            "The ghostly ledger snapped shut as Mira pressed her palm to the cover.",
            tier3_text,
        )
        self.assertEqual(
            runtime["chapter_summaries"][0]["summary"],
            "Mira bargains with the archive ghosts and learns the ledger answers to blood.",
        )
        self.assertEqual(runtime["continuation_anchor"]["chapter"], 1)
        self.assertIn("ghostly ledger snapped shut", runtime["continuation_anchor"]["tail"])

    def test_compose_context_preserves_newer_runtime_continuity_over_disk_backfill(self) -> None:
        template_dna = {"principles": [], "dialogue_patterns": []}
        story_bible = {
            "metadata": {"title": "Artifact Recall"},
            "world": {"rules": ["Magic demands a memory toll."]},
            "characters": [{"name": "Mira"}],
            "conflicts": {"main_conflict": "Mira must cross the haunted archive."},
        }
        structure_map = {
            "target_chapters": 6,
            "stage_contracts": [
                {
                    "stage_id": "stage_01",
                    "template_title": "Opening",
                    "chapter_start": 1,
                    "chapter_end": 4,
                    "story_goal": "Escalate the archive crossing.",
                    "must_keep": [],
                    "escalation_target": "Raise pressure.",
                },
            ],
            "chapter_plan": [
                {"chapter": 1, "objective": "Mira enters the archive."},
                {"chapter": 2, "objective": "Mira survives the blood pact."},
                {"chapter": 3, "objective": "Mira opens the sealed ledger."},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            book_root = Path(temp_dir)
            chapter_dir = book_root / "chapters" / "0001"
            chapter_dir.mkdir(parents=True, exist_ok=True)
            (chapter_dir / "summary.json").write_text(
                json.dumps({"chapter": 1, "summary": "Older disk summary."}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (chapter_dir / "draft.md").write_text(
                "# Chapter 1\n\nOlder disk tail.\n",
                encoding="utf-8",
            )

            runtime_state = {
                "book_root": str(book_root),
                "character_states": [
                    {
                        "name": "Mira",
                        "status": "active",
                        "survival_status": "active",
                        "current_state": "already carrying the opened ledger",
                        "position": "inner archive",
                        "last_updated_chapter": 2,
                    },
                ],
                "irreversible_events": [],
                "active_threads": [
                    {
                        "thread_id": "main_conflict",
                        "title": "Mira must cross the haunted archive.",
                        "status": "active",
                        "priority": "P0",
                        "introduced_chapter": 1,
                        "last_updated_chapter": 2,
                        "due_chapter": 4,
                    },
                ],
                "thread_ledger": [],
                "chapter_summaries": [{"chapter": 2, "summary": "Newer in-memory summary."}],
                "continuation_anchor": {
                    "chapter": 2,
                    "tail": "Newer in-memory tail.",
                    "source": "runtime_state",
                },
                "recent_progress": {
                    "chapter": 2,
                    "summary": "Newer in-memory summary.",
                    "tail": "Newer in-memory tail.",
                },
                "foreshadows": [],
                "foreshadow_ledger": [],
                "state_deltas": [],
                "author_intent": "Keep the latest continuity visible.",
                "current_focus": "Mira studies the opened ledger.",
                "runtime_prompt_view": {},
            }

            bundle, _, runtime = compose_context(
                template_dna=template_dna,
                story_bible=story_bible,
                structure_map=structure_map,
                runtime_state=runtime_state,
                chapter_no=3,
            )

        self.assertEqual(runtime["continuation_anchor"]["chapter"], 2)
        self.assertEqual(runtime["continuation_anchor"]["tail"], "Newer in-memory tail.")
        self.assertEqual(runtime["recent_progress"]["chapter"], 2)
        self.assertEqual(runtime["recent_progress"]["summary"], "Newer in-memory summary.")
        self.assertEqual(bundle["continuation_anchor"]["chapter"], 2)
        self.assertEqual(bundle["recent_progress"]["summary"], "Newer in-memory summary.")


if __name__ == "__main__":
    unittest.main()

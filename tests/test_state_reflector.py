from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from template_novel_engine.state_reflector import apply_t6_state_reflection, build_runtime_prompt_view


class RuntimePromptViewTests(unittest.TestCase):
    def test_prompt_view_prefers_due_threads_and_due_foreshadows(self) -> None:
        runtime = {
            "active_threads": [
                {
                    "thread_id": "late_priority",
                    "title": "远期支线",
                    "priority": "P0",
                    "due_chapter": 9,
                    "last_updated_chapter": 2,
                    "status": "active",
                },
                {
                    "thread_id": "main",
                    "title": "遗迹苏醒",
                    "priority": "P1",
                    "due_chapter": 3,
                    "last_updated_chapter": 1,
                    "status": "active",
                },
            ],
            "foreshadows": [
                {
                    "foreshadow_id": "fs_late",
                    "description": "更晚才需要兑现的线索",
                    "due_chapter": 8,
                    "last_updated_chapter": 2,
                    "status": "埋入",
                },
                {
                    "foreshadow_id": "fs_01",
                    "description": "石门后的呼吸声",
                    "due_chapter": 3,
                    "last_updated_chapter": 1,
                    "status": "埋入",
                },
            ],
            "chapter_summaries": [{"chapter": 2, "summary": "林澈发现石门后的甬道。"}],
        }

        view = build_runtime_prompt_view(runtime, chapter_no=3, cfg={"enabled": True, "shadow_mode": False})

        selected = view.get("selected", {})
        self.assertEqual(selected.get("active_threads", [])[0]["thread_id"], "main")
        self.assertEqual(selected.get("foreshadows_due", [])[0]["foreshadow_id"], "fs_01")


class RuntimeQualityHistoryTests(unittest.TestCase):
    def test_apply_t6_state_reflection_appends_runtime_quality_history(self) -> None:
        runtime_after, _, _ = apply_t6_state_reflection(
            runtime_state={
                "active_threads": [
                    {
                        "thread_id": "main",
                        "title": "遗迹苏醒",
                        "status": "active",
                        "priority": "P1",
                        "due_chapter": 3,
                        "last_updated_chapter": 1,
                    }
                ],
                "chapter_summaries": [],
                "foreshadows": [],
                "foreshadow_ledger": [],
                "state_deltas": [],
            },
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            chapter_no=2,
            draft_markdown="# 第2章\n\n## 正文\n林澈推进调查。\n",
            chapter_summary="林澈推进调查。",
            contract={"chapter_objective": "推进遗迹主线", "stage_range": {"chapter_end": 4}},
            alignment={"pass": True},
            chapter_analysis={
                "character_states": [],
                "foreshadows": [],
            },
        )

        self.assertEqual(
            runtime_after.get("quality_history", []),
            [{"chapter": 2, "pass": True, "hard_failures": 0, "warnings": 0}],
        )

    def test_apply_t6_state_reflection_prefers_after_pass_and_after_failures(self) -> None:
        runtime_after, _, _ = apply_t6_state_reflection(
            runtime_state={
                "active_threads": [
                    {
                        "thread_id": "main",
                        "title": "遗迹苏醒",
                        "status": "active",
                        "priority": "P1",
                        "due_chapter": 3,
                        "last_updated_chapter": 1,
                    }
                ],
                "chapter_summaries": [],
                "foreshadows": [],
                "foreshadow_ledger": [],
                "state_deltas": [],
            },
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            chapter_no=3,
            draft_markdown="# 第3章\n\n## 正文\n林澈继续逼近遗迹核心。\n",
            chapter_summary="林澈继续逼近遗迹核心。",
            contract={"chapter_objective": "推进遗迹主线", "stage_range": {"chapter_end": 4}},
            alignment={"pass": True},
            chapter_analysis={
                "character_states": [],
                "foreshadows": [],
            },
            audit_report={
                "pass": True,
                "after": {
                    "pass": False,
                    "failures": [
                        {"severity": "error"},
                        {"severity": "warning"},
                    ],
                },
            },
        )

        self.assertEqual(
            runtime_after.get("quality_history", []),
            [{"chapter": 3, "pass": False, "hard_failures": 1, "warnings": 1}],
        )


if __name__ == "__main__":
    unittest.main()

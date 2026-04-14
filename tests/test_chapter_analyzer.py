from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from template_novel_engine.chapter_analyzer import analyze_chapter


class ChapterAnalyzerSignalTests(unittest.TestCase):
    def test_analyze_chapter_reports_progress_and_ending_shape(self) -> None:
        result = analyze_chapter(
            chapter_no=3,
            draft_markdown=(
                "# 第3章\n\n## 正文\n"
                "林澈沿着石门后的甬道追下去，终于确认异响来自地底祭坛。\n"
                "临近结尾，他看见祭坛中央的火光突然亮起。\n"
            ),
            chapter_summary="林澈追查异响，发现祭坛火光。",
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            runtime_state={"active_threads": [{"thread_id": "main_conflict", "title": "地下遗迹苏醒"}]},
        )

        self.assertIn("continuation_signals", result)
        self.assertIn("progress_signals", result)
        self.assertIn("thread_updates", result)
        self.assertIn("foreshadow_updates", result)
        self.assertIn("ending_shape", result)
        self.assertIn("repetition_markers", result)
        self.assertEqual(result["progress_signals"]["objective_status"], "fulfilled")
        self.assertEqual(result["ending_shape"]["type"], "reveal")

    def test_analyze_chapter_summarizes_threads_foreshadows_and_repetition_markers(self) -> None:
        result = analyze_chapter(
            chapter_no=4,
            draft_markdown=(
                "# 第4章\n\n## 正文\n"
                "林澈再次走到石门前，石门上的裂纹比昨夜更深。\n"
                "他意识到地下遗迹的震动和主线危机已经逼近，决定继续推进调查。\n"
                "这道石门、这道石门的回响，让他想起此前埋下的线索与异样。\n"
                "结尾处，他忽然明白祭坛纹路指向更深处的秘密。\n"
            ),
            chapter_summary="林澈推进地下遗迹调查，意识到石门线索指向更深秘密。",
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            runtime_state={
                "active_threads": [
                    {"thread_id": "main_conflict", "title": "地下遗迹苏醒"},
                    {"thread_id": "gate_mystery", "title": "石门异响之谜"},
                ]
            },
        )

        self.assertIn("地下遗迹苏醒", result["progress_signals"]["touched_threads"])
        self.assertIn("石门异响之谜", result["thread_updates"]["advanced"])
        self.assertTrue(result["foreshadow_updates"]["planted"])
        self.assertEqual(result["foreshadow_updates"]["resolved"], [])
        self.assertIn("石门", result["continuation_signals"]["carry_forward_elements"])
        self.assertIn("石门", result["repetition_markers"]["repeated_terms"])

    def test_analyze_chapter_does_not_touch_unrelated_thread_from_partial_terms(self) -> None:
        result = analyze_chapter(
            chapter_no=5,
            draft_markdown=(
                "# 第5章\n\n## 正文\n"
                "林澈沿着地道继续下行，听见远处传来断续回声。\n"
                "他决定先确认脚下路径是否安全，再继续推进。\n"
            ),
            chapter_summary="林澈继续探索地道。",
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            runtime_state={
                "active_threads": [
                    {"thread_id": "archive", "title": "地下遗迹苏醒"},
                    {"thread_id": "gate", "title": "石门异响之谜"},
                ]
            },
        )

        self.assertEqual(result["progress_signals"]["touched_threads"], [])
        self.assertEqual(result["thread_updates"]["advanced"], [])

    def test_analyze_chapter_does_not_flag_repetition_from_summary_echo_only(self) -> None:
        result = analyze_chapter(
            chapter_no=6,
            draft_markdown=(
                "# 第6章\n\n## 正文\n"
                "林澈走进祭坛大厅，观察四周残留的火痕。\n"
                "他停在裂开的石阶前，判断下一步该如何靠近核心区域。\n"
            ),
            chapter_summary="林澈进入祭坛大厅，观察祭坛周围痕迹。",
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            runtime_state={"active_threads": []},
        )

        self.assertEqual(result["repetition_markers"]["repeated_terms"], [])
        self.assertFalse(result["repetition_markers"]["has_heavy_repetition"])


if __name__ == "__main__":
    unittest.main()

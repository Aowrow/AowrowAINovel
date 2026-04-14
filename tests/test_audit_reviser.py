from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from template_novel_engine.audit_reviser import run_t7_audit, run_t7_batch_auditor


class AuditReviserRuleTests(unittest.TestCase):
    def test_batch_auditor_carries_runtime_state_forward_between_chapters(self) -> None:
        revised_packages, summary = run_t7_batch_auditor(
            story_bible={
                "metadata": {"chapter_word_target": 100},
                "characters": [{"name": "林澈", "role": "protagonist"}],
            },
            structure_map={},
            runtime_state={
                "chapter_summaries": [{"chapter": 1, "summary": "林澈听见石门后的异响。"}],
                "active_threads": [
                    {"thread_id": "main_conflict", "title": "异响真相", "due_chapter": 2, "status": "active"},
                ],
                "foreshadows": [],
                "foreshadow_ledger": [],
                "character_states": [],
            },
            chapter_packages=[
                {
                    "chapter": 2,
                    "draft_markdown": "# 第2章\n\n## 正文\n林澈核对石门后的异响，并确认祭坛火光秘密已经浮出一角。\n",
                    "chapter_summary": "林澈核对石门后的异响，并确认祭坛火光秘密已经浮出一角。",
                    "contract": {
                        "chapter_objective": "核对异响来源",
                        "stage_id": "stage_01",
                        "length_control_enabled": False,
                    },
                    "alignment_report": {"pass": True},
                    "state_delta": {
                        "thread_actions": [
                            {
                                "action": "推进",
                                "thread_id": "main_conflict",
                                "title": "异响真相",
                                "note": "异响主线在本章获得推进",
                            },
                        ],
                        "foreshadow_actions": [
                            {
                                "action": "埋入",
                                "foreshadow_id": "fs_002",
                                "due_chapter": 3,
                                "description": "石壁上的三重敲击声",
                            }
                        ],
                        "character_updates": [
                            {
                                "name": "林澈",
                                "status_hint": "active",
                                "state_after": "重伤未愈",
                                "note": "上一章负伤后仍未恢复",
                            },
                        ],
                    },
                },
                {
                    "chapter": 3,
                    "draft_markdown": (
                        "# 第3章\n\n## 正文\n"
                        "林澈神完气足，像从未受过伤一样向前推进，只顾低头观察地面，没有回应祭坛火光秘密，也没有推动此前那条主线。\n"
                    ),
                    "chapter_summary": "林澈继续前行。",
                    "contract": {
                        "chapter_objective": "继续深入甬道",
                        "stage_id": "stage_01",
                        "length_control_enabled": False,
                    },
                    "alignment_report": {"pass": True},
                    "state_delta": {},
                },
            ],
            auto_revise=False,
        )

        self.assertEqual(len(revised_packages), 2)
        chapter_three_failures = {
            item["rule_id"] for item in revised_packages[1]["t7_audit_report"]["after"]["failures"]
        }
        self.assertIn("PG_ACTIVE_THREAD_STATIC", chapter_three_failures)
        self.assertIn("FG_DUE_FORESHADOW_IGNORED", chapter_three_failures)
        self.assertIn("CC_STATE_CONTRADICTION", chapter_three_failures)
        self.assertFalse(summary["pass"])

    def test_audit_flags_missing_objective_fulfillment(self) -> None:
        report = run_t7_audit(
            chapter_no=2,
            draft_markdown="# 第2章\n\n## 正文\n林澈只是站在门前回忆过去，没有推进任何行动。\n\n## 本章模板对齐点\n- 阶段: stage_01\n",
            contract={
                "chapter_objective": "进入石门后的地下通道",
                "stage_id": "stage_01",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={
                "chapter_summaries": [{"chapter": 1, "summary": "林澈打开石门。"}],
                "active_threads": [{"thread_id": "main_conflict", "title": "地下遗迹苏醒", "due_chapter": 2}],
                "foreshadows": [{"foreshadow_id": "fs_001", "status": "埋入", "due_chapter": 2, "description": "石门后的异响"}],
            },
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertIn("PG_OBJECTIVE_NOT_FULFILLED", rule_ids)

    def test_audit_does_not_treat_generic_motion_as_objective_fulfillment(self) -> None:
        report = run_t7_audit(
            chapter_no=4,
            draft_markdown=(
                "# 第4章\n\n## 正文\n"
                "林澈决定先撤出祭坛外围，准备明日再来，眼下仍没有逼近核心。\n\n"
                "## 本章模板对齐点\n- 阶段: stage_02\n"
            ),
            contract={
                "chapter_objective": "逼近祭坛核心",
                "stage_id": "stage_02",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={},
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertIn("PG_OBJECTIVE_NOT_FULFILLED", rule_ids)

    def test_audit_requires_active_thread_movement_for_progression(self) -> None:
        report = run_t7_audit(
            chapter_no=3,
            draft_markdown=(
                "# 第3章\n\n## 正文\n"
                "林澈终于进入石门后的地下通道，但沿路只是观察墙面的纹路，没有触及地下遗迹苏醒这条主线。\n\n"
                "## 本章模板对齐点\n- 阶段: stage_01\n"
            ),
            contract={
                "chapter_objective": "进入石门后的地下通道",
                "stage_id": "stage_01",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={
                "active_threads": [
                    {"thread_id": "main_conflict", "title": "地下遗迹苏醒", "due_chapter": 3},
                ],
            },
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertIn("PG_ACTIVE_THREAD_STATIC", rule_ids)

    def test_audit_does_not_require_background_thread_movement_when_not_due(self) -> None:
        report = run_t7_audit(
            chapter_no=3,
            draft_markdown=(
                "# 第3章\n\n## 正文\n"
                "林澈进入石门后的地下通道，在潮湿甬道里确认了入口后的落脚点，还发现前方留有新近踩出的脚印。\n\n"
                "## 本章模板对齐点\n- 阶段: stage_01\n"
            ),
            contract={
                "chapter_objective": "进入石门后的地下通道",
                "stage_id": "stage_01",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={
                "active_threads": [
                    {"thread_id": "side_thread", "title": "祭坛火光秘密", "due_chapter": 8},
                ],
            },
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertNotIn("PG_ACTIVE_THREAD_STATIC", rule_ids)

    def test_audit_accepts_valid_objective_progression(self) -> None:
        report = run_t7_audit(
            chapter_no=4,
            draft_markdown=(
                "# 第4章\n\n## 正文\n"
                "林澈逼近祭坛核心，先撬开封住台阶的石板，再顺着回响查明异响来源，证实地下遗迹正在苏醒。\n\n"
                "## 本章模板对齐点\n- 阶段: stage_02\n"
            ),
            contract={
                "chapter_objective": "逼近祭坛核心",
                "stage_id": "stage_02",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={
                "active_threads": [
                    {"thread_id": "main_conflict", "title": "地下遗迹苏醒", "due_chapter": 4},
                ],
            },
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertNotIn("PG_OBJECTIVE_NOT_FULFILLED", rule_ids)
        self.assertNotIn("PG_ACTIVE_THREAD_STATIC", rule_ids)

    def test_audit_flags_heavy_repetition_against_recent_progress(self) -> None:
        report = run_t7_audit(
            chapter_no=3,
            draft_markdown=(
                "# 第3章\n\n## 正文\n"
                "林澈再次站到石门前。石门没有变化，石门仍旧冰冷，石门的裂纹也和上一章一样。\n\n"
                "## 本章模板对齐点\n- 阶段: stage_01\n"
            ),
            contract={
                "chapter_objective": "确认石门后的新变化",
                "stage_id": "stage_01",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={
                "chapter_summaries": [{"chapter": 2, "summary": "上一章已经写过林澈站到石门前观察裂纹。"}],
            },
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertIn("RP_HEAVY_TERM_REPETITION", rule_ids)

    def test_audit_flags_character_state_contradiction(self) -> None:
        report = run_t7_audit(
            chapter_no=4,
            draft_markdown=(
                "# 第4章\n\n## 正文\n"
                "林澈此刻神完气足，步伐轻快，像从未受过伤一样冲向祭坛。\n\n"
                "## 本章模板对齐点\n- 阶段: stage_02\n"
            ),
            contract={
                "chapter_objective": "逼近祭坛核心",
                "stage_id": "stage_02",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={
                "character_states": [
                    {"name": "林澈", "current_state": "重伤未愈，行动艰难", "last_updated_chapter": 3},
                ],
            },
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertIn("CC_STATE_CONTRADICTION", rule_ids)

    def test_audit_flags_due_foreshadow_left_unadvanced(self) -> None:
        report = run_t7_audit(
            chapter_no=5,
            draft_markdown=(
                "# 第5章\n\n## 正文\n"
                "林澈进入甬道深处，只顾着检查地面的血迹，没有回应此前埋下的异常呼吸声。\n\n"
                "## 本章模板对齐点\n- 阶段: stage_02\n"
            ),
            contract={
                "chapter_objective": "继续深入甬道",
                "stage_id": "stage_02",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={
                "foreshadows": [
                    {"foreshadow_id": "fs_002", "status": "埋入", "due_chapter": 5, "description": "石门后的异响"},
                ],
            },
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertIn("FG_DUE_FORESHADOW_IGNORED", rule_ids)

    def test_audit_flags_duplicate_and_false_resolved_foreshadows(self) -> None:
        report = run_t7_audit(
            chapter_no=6,
            draft_markdown=(
                "# 第6章\n\n## 正文\n"
                "林澈重新提起石门后的异响，又说那个真相已经解决，可场面里并没有任何揭开或证实。\n\n"
                "## 本章模板对齐点\n- 阶段: stage_02\n"
            ),
            contract={
                "chapter_objective": "核对异响来源",
                "stage_id": "stage_02",
                "length_control_enabled": False,
            },
            alignment_report={"pass": True},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={},
            runtime_state={
                "foreshadows": [
                    {
                        "foreshadow_id": "fs_002",
                        "status": "埋入",
                        "due_chapter": 6,
                        "description": "石门后的异响",
                    },
                    {
                        "foreshadow_id": "fs_003",
                        "status": "resolved",
                        "due_chapter": 5,
                        "description": "祭坛下的真相",
                    },
                ],
                "foreshadow_ledger": [
                    {"foreshadow_id": "fs_001", "status": "open", "note": "石门后的异响"},
                ],
            },
        )

        rule_ids = {item["rule_id"] for item in report["failures"]}
        self.assertIn("FG_DUPLICATE_FORESHADOW", rule_ids)
        self.assertIn("FG_FALSE_RESOLUTION", rule_ids)

    def test_audit_keeps_alignment_findings_inside_audit_output(self) -> None:
        report = run_t7_audit(
            chapter_no=2,
            draft_markdown="# 第2章\n\n## 正文\n林澈进入通道。\n",
            contract={
                "chapter_objective": "进入通道",
                "stage_id": "wrong_stage",
                "length_control_enabled": False,
            },
            alignment_report={"pass": False, "detail": "objective drift"},
            story_bible={"characters": [{"name": "林澈", "role": "protagonist"}]},
            structure_map={
                "stage_contracts": [
                    {"stage_id": "stage_01", "chapter_start": 1, "chapter_end": 3},
                ]
            },
            runtime_state={},
        )

        self.assertIn("template_alignment", report["category_results"])
        self.assertIn("failures", report)
        self.assertNotIn("alignment_report", report)


if __name__ == "__main__":
    unittest.main()

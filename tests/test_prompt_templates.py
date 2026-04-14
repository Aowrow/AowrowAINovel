from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from template_novel_engine.prompt_templates import build_chapter_prompt_payload
from template_novel_engine.model_writer import build_chapter_prompts
from template_novel_engine.context_engine import compose_context
from template_novel_engine.chapter_orchestrator import build_precheck


class PromptTemplatePayloadTests(unittest.TestCase):
    def test_compose_context_bundle_feeds_prompt_and_precheck_with_current_continuity_keys(self) -> None:
        template_dna = {
            "core_premise": "遗迹苏醒",
            "template_formulas": [],
            "dialogue_patterns": [],
            "principles": [],
            "reusable_motifs": [],
        }
        story_bible = {
            "metadata": {"title": "测试书", "chapter_word_target": 3000},
            "premise": {"logline": "主角深入遗迹", "theme": "代价"},
            "conflicts": {"main_conflict": "遗迹正在苏醒", "secondary_conflicts": []},
            "world": {"rules": ["石门只能开启一次"], "locations": ["地宫"]},
            "constraints": {"must_have": [], "must_avoid": []},
            "characters": [{"name": "林澈", "role": "protagonist"}],
        }
        structure_map = {
            "stage_contracts": [
                {
                    "stage_id": "stage_01",
                    "chapter_start": 1,
                    "chapter_end": 3,
                    "story_goal": "推进遗迹主线",
                    "must_keep": ["主角主动"],
                    "template_title": "遗迹开门",
                    "escalation_target": "让地下威胁显形",
                }
            ],
            "chapter_plan": [
                {"chapter": 2, "title": "地底回声", "objective": "承接地底异动"},
            ],
        }
        runtime_state = {
            "chapter_summaries": [{"chapter": 1, "summary": "上一章打开石门"}],
            "continuation_anchor": {
                "chapter": 1,
                "tail": "冷风灌入地底。",
                "source": "runtime_state",
            },
            "recent_progress": {
                "chapter": 1,
                "summary": "上一章打开石门",
                "tail": "冷风灌入地底。",
                "anti_repetition": ["不要重复石门开启场景"],
            },
            "active_threads": [
                {"thread_id": "main_conflict", "title": "遗迹正在苏醒", "due_chapter": 2},
            ],
            "thread_ledger": [],
            "character_states": [{"name": "林澈", "current_state": "警惕", "last_updated_chapter": 1}],
            "irreversible_events": [],
            "foreshadows": [],
            "foreshadow_ledger": [],
            "state_deltas": [],
            "runtime_prompt_view": {},
        }
        contract = {
            "chapter_objective": "承接地底异动",
            "must_keep": ["主角主动"],
        }

        context_bundle, _, _ = compose_context(
            template_dna=template_dna,
            story_bible=story_bible,
            structure_map=structure_map,
            runtime_state=runtime_state,
            chapter_no=2,
        )
        precheck = build_precheck(contract, context_bundle, chapter_no=2)
        payload = build_chapter_prompt_payload(
            contract=contract,
            context_bundle=context_bundle,
            precheck=precheck,
            anti_ai_style_cfg={"enabled": True},
        )

        self.assertEqual(precheck["warnings"], ["避免重复：不要重复石门开启场景"])
        self.assertIn("上一章摘要：上一章打开石门", payload["user_prompt"])
        self.assertIn("上一章尾部：冷风灌入地底。", payload["user_prompt"])

    def test_prompt_payload_contains_continuation_and_precheck(self) -> None:
        payload = build_chapter_prompt_payload(
            contract={"chapter_objective": "承接地底异动", "must_keep": ["主角主动"]},
            context_bundle={
                "continuation_anchor": {"tail": "冷风灌入地底。"},
                "recent_progress": {
                    "summary": "上一章打开石门",
                    "anti_repetition": ["不要重复石门开启场景"],
                },
            },
            precheck={"warnings": ["当前章缺少明确推进线程"]},
            anti_ai_style_cfg={"enabled": True},
        )

        self.assertIn("上一章打开石门", payload["user_prompt"])
        self.assertIn("当前章缺少明确推进线程", payload["user_prompt"])

    def test_build_chapter_prompts_wires_payload_without_duplicate_anti_ai_block(self) -> None:
        system_prompt, user_prompt = build_chapter_prompts(
            template_dna={
                "core_premise": "遗迹正在苏醒",
                "template_formulas": [],
                "dialogue_patterns": [],
                "principles": [],
                "reusable_motifs": [],
            },
            story_bible={
                "metadata": {"title": "测试书", "chapter_word_target": 3000},
                "premise": {"logline": "主角被迫深入遗迹", "theme": "主动选择的代价"},
                "conflicts": {"main_conflict": "地底异动正在升级", "secondary_conflicts": []},
                "world": {"rules": ["石门只能开启一次"], "locations": ["地宫"]},
                "constraints": {"must_have": [], "must_avoid": []},
                "characters": [{"name": "林澈", "role": "protagonist"}],
            },
            contract={
                "chapter_title": "地底回声",
                "chapter_objective": "承接地底异动",
                "stage_id": "stage_01",
                "stage_range": {"chapter_start": 1, "chapter_end": 5},
                "template_anchor": "遗迹开门",
                "stage_goal": "推进遗迹主线",
                "escalation_target": "让地下威胁显形",
                "must_keep": ["主角主动"],
                "forbidden": ["不得跳过阶段"],
                "planned_beats": ["进入石门后确认异响来源"],
            },
            context_bundle={
                "continuation_anchor": {"tail": "冷风灌入地底。"},
                "recent_progress": {
                    "summary": "上一章打开石门",
                    "anti_repetition": ["不要重复石门开启场景"],
                },
                "prompt_blocks": {"full_context": "线程必须继续推进。"},
            },
            chapter_no=2,
            anti_ai_style_cfg={"enabled": True},
            precheck={"warnings": ["当前章缺少明确推进线程"]},
        )

        self.assertTrue(system_prompt.strip())
        self.assertIn("[StructuredChapterPayload]", user_prompt)
        self.assertIn("上一章打开石门", user_prompt)
        self.assertIn("当前章缺少明确推进线程", user_prompt)
        self.assertEqual(user_prompt.count("【Anti-AI-Style】"), 1)


if __name__ == "__main__":
    unittest.main()

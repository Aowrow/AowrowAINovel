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


from template_novel_engine.asset_store import AssetStore


class AssetStoreTests(unittest.TestCase):
    def test_write_chapter_package_skips_redundant_files_and_exports_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AssetStore(Path(tmp))

            chapter_no = store.write_chapter_package(
                {
                    "chapter": 1,
                    "draft_markdown": "# 第1章\n\n## 正文\n正文\n",
                    "chapter_summary": "摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": True},
                    "t7_diff_report_md": "",
                    "state_delta": {},
                    "alignment_report": {},
                }
            )

            chapter_dir = Path(tmp) / "chapters" / f"{chapter_no:04d}"
            self.assertFalse((chapter_dir / "package.json").exists())
            self.assertFalse((chapter_dir / "alignment.json").exists())
            self.assertFalse((chapter_dir / "diff.md").exists())
            self.assertFalse((Path(tmp) / "exports" / "第1章.txt").exists())
            self.assertFalse((Path(tmp) / "exports" / "全书.txt").exists())

    def test_write_chapter_package_writes_optional_files_when_storage_toggles_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AssetStore(Path(tmp))

            store.write_chapter_package(
                {
                    "chapter": 2,
                    "draft_markdown": "# 第2章\n\n## 正文\n正文\n\n## 本章模板对齐点\n- 节点\n",
                    "chapter_summary": "第二章摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": False},
                    "t7_diff_report_md": "- old\n+ new\n",
                    "state_delta": {},
                    "alignment_report": {"pass": True},
                },
                storage_cfg={
                    "write_debug_package": True,
                    "write_alignment_file": True,
                    "export_plain_text": True,
                    "export_full_book": True,
                },
            )

            chapter_dir = Path(tmp) / "chapters" / "0002"
            self.assertTrue((chapter_dir / "package.json").exists())
            self.assertTrue((chapter_dir / "alignment.json").exists())
            self.assertTrue((chapter_dir / "diff.md").exists())
            self.assertTrue((Path(tmp) / "exports" / "第2章.txt").exists())
            self.assertTrue((Path(tmp) / "exports" / "全书.txt").exists())

    def test_write_chapter_package_uses_nearest_project_config_for_book_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            book_root = project_root / "books" / "demo"
            project_root.joinpath("template_novel_engine.config.json").write_text(
                json.dumps(
                    {
                        "storage": {
                            "write_debug_package": True,
                            "write_alignment_file": True,
                            "export_plain_text": True,
                            "export_full_book": True,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            store = AssetStore(book_root)

            store.write_chapter_package(
                {
                    "chapter": 5,
                    "draft_markdown": "# 第5章\n\n## 正文\n正文\n\n## 本章模板对齐点\n- 节点\n",
                    "chapter_summary": "第五章摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": True},
                    "t7_diff_report_md": "- old\n+ new\n",
                    "state_delta": {},
                    "alignment_report": {"pass": True},
                }
            )

            chapter_dir = book_root / "chapters" / "0005"
            self.assertTrue((chapter_dir / "package.json").exists())
            self.assertTrue((chapter_dir / "alignment.json").exists())
            self.assertTrue((chapter_dir / "diff.md").exists())
            self.assertTrue((book_root / "exports" / "第5章.txt").exists())
            self.assertTrue((book_root / "exports" / "全书.txt").exists())

    def test_rewriting_chapter_with_disabled_toggles_removes_stale_optional_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AssetStore(Path(tmp))

            store.write_chapter_package(
                {
                    "chapter": 6,
                    "draft_markdown": "# 第6章\n\n## 正文\n初稿\n\n## 本章模板对齐点\n- 节点\n",
                    "chapter_summary": "第六章摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": True},
                    "t7_diff_report_md": "- old\n+ new\n",
                    "state_delta": {},
                    "alignment_report": {"pass": True},
                },
                storage_cfg={
                    "write_debug_package": True,
                    "write_alignment_file": True,
                    "export_plain_text": True,
                    "export_full_book": True,
                },
            )
            full_book_path = Path(tmp) / "exports" / "全书.txt"
            original_full_book = full_book_path.read_text(encoding="utf-8")

            store.write_chapter_package(
                {
                    "chapter": 6,
                    "draft_markdown": "# 第6章\n\n## 正文\n重写\n",
                    "chapter_summary": "第六章重写摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": False},
                    "t7_diff_report_md": "",
                    "state_delta": {},
                    "alignment_report": {"pass": False},
                },
                storage_cfg={
                    "write_debug_package": False,
                    "write_alignment_file": False,
                    "export_plain_text": False,
                    "export_full_book": False,
                },
            )

            chapter_dir = Path(tmp) / "chapters" / "0006"
            self.assertFalse((chapter_dir / "package.json").exists())
            self.assertFalse((chapter_dir / "alignment.json").exists())
            self.assertFalse((chapter_dir / "diff.md").exists())
            self.assertFalse((Path(tmp) / "exports" / "第6章.txt").exists())
            self.assertTrue(full_book_path.exists())
            self.assertEqual(full_book_path.read_text(encoding="utf-8"), original_full_book)

    def test_disabling_full_book_export_for_single_rewrite_keeps_existing_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AssetStore(Path(tmp))
            exports_dir = Path(tmp) / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            full_book_path = exports_dir / "全书.txt"
            original_full_book = "第1章\n\n旧内容\n\n========================================\n\n第2章\n\n其他章节内容\n"
            full_book_path.write_text(original_full_book, encoding="utf-8")

            store.write_chapter_package(
                {
                    "chapter": 6,
                    "draft_markdown": "# 第6章\n\n## 正文\n保留聚合文件\n",
                    "chapter_summary": "第六章改写摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": True},
                    "t7_diff_report_md": "",
                    "state_delta": {},
                    "alignment_report": {},
                },
                storage_cfg={
                    "write_debug_package": False,
                    "write_alignment_file": False,
                    "export_plain_text": False,
                    "export_full_book": False,
                },
            )

            self.assertFalse((exports_dir / "第6章.txt").exists())
            self.assertTrue(full_book_path.exists())
            self.assertEqual(full_book_path.read_text(encoding="utf-8"), original_full_book)

    def test_rewriting_same_chapter_replaces_section_in_full_book_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AssetStore(Path(tmp))

            store.write_chapter_package(
                {
                    "chapter": 2,
                    "draft_markdown": "# 第2章\n\n## 正文\n旧版本正文\n\n## 本章模板对齐点\n- 节点\n",
                    "chapter_summary": "旧摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": True},
                    "t7_diff_report_md": "",
                    "state_delta": {},
                    "alignment_report": {},
                },
                storage_cfg={
                    "export_plain_text": True,
                    "export_full_book": True,
                },
            )
            store.write_chapter_package(
                {
                    "chapter": 3,
                    "draft_markdown": "# 第3章\n\n## 正文\n第三章正文\n",
                    "chapter_summary": "第三章摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": True},
                    "t7_diff_report_md": "",
                    "state_delta": {},
                    "alignment_report": {},
                },
                storage_cfg={
                    "export_plain_text": True,
                    "export_full_book": True,
                },
            )
            store.write_chapter_package(
                {
                    "chapter": 2,
                    "draft_markdown": "# 第2章\n\n## 正文\n新版本正文\n",
                    "chapter_summary": "新摘要",
                    "context_bundle": {},
                    "contract": {},
                    "chapter_analysis": {},
                    "t7_audit_report": {"pass": True},
                    "t7_diff_report_md": "",
                    "state_delta": {},
                    "alignment_report": {},
                },
                storage_cfg={
                    "export_plain_text": True,
                    "export_full_book": True,
                },
            )

            full_book = (Path(tmp) / "exports" / "全书.txt").read_text(encoding="utf-8")
            sections = [section for section in full_book.split("\n\n========================================\n\n") if section.strip()]
            chapter_two_sections = [section for section in sections if section.startswith("第2章\n\n")]

            self.assertEqual(len(chapter_two_sections), 1)
            self.assertIn("新版本正文", full_book)
            self.assertNotIn("旧版本正文", full_book)
            self.assertIn("第3章", full_book)

    def test_write_quality_history_recovers_from_malformed_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AssetStore(Path(tmp))
            history_path = Path(tmp) / "runtime" / "quality_history.json"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text("{not valid json", encoding="utf-8")

            store.write_quality_history(
                7,
                {
                    "pass": False,
                    "after": {
                        "failures": [
                            {"severity": "error"},
                            {"severity": "warning"},
                        ]
                    },
                },
            )

            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload,
                {
                    "chapters": [
                        {"chapter": 7, "pass": False, "hard_failures": 1, "warnings": 1},
                    ]
                },
            )

    def test_write_quality_history_appends_and_replaces_duplicate_chapter_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AssetStore(Path(tmp))

            store.write_quality_history(
                3,
                {
                    "pass": False,
                    "after": {
                        "failures": [
                            {"severity": "error"},
                            {"severity": "warning"},
                        ]
                    },
                },
            )
            store.write_quality_history(
                3,
                {
                    "pass": True,
                    "after": {
                        "failures": [
                            {"severity": "warning"},
                        ]
                    },
                },
            )
            store.write_quality_history(
                4,
                {
                    "pass": False,
                    "after": {
                        "failures": [
                            {"severity": "error"},
                            {"severity": "error"},
                        ]
                    },
                },
            )

            payload = json.loads((Path(tmp) / "runtime" / "quality_history.json").read_text(encoding="utf-8"))
            self.assertEqual(
                payload,
                {
                    "chapters": [
                        {"chapter": 3, "pass": True, "hard_failures": 0, "warnings": 1},
                        {"chapter": 4, "pass": False, "hard_failures": 2, "warnings": 0},
                    ]
                },
            )


if __name__ == "__main__":
    unittest.main()

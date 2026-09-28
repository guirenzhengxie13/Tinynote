import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tinynote.storage import ExternalEditError, NoteStore, note_name


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = NoteStore(self.root, ["随手记.md", "灵感.md"])

    def contents(self):
        return self.store.current.read_text(encoding="utf-8")

    def test_replace_in_middle_keeps_both_sides(self):
        self.store.save_document("甲乙丙丁\n下一行")
        self.store.save_document("甲乙新丙丁\n下一行")
        self.assertEqual(self.contents(), "甲乙新丙丁\n下一行\n")

    def test_restart_retains_unsplit_live_line(self):
        self.store.save_document("选词确认后已保存")
        restarted = NoteStore(self.root, ["随手记.md", "灵感.md"])
        self.assertEqual(restarted.text, "选词确认后已保存\n")

    def test_backspace_and_delete_preserve_rest(self):
        self.store.save_document("历史\n待删\n保留")
        self.store.save_document("历史\n\n保留")
        self.assertEqual(self.contents(), "历史\n\n保留\n")

    def test_utf8_bom_and_crlf_are_supported(self):
        self.store.current.write_bytes(b"\xef\xbb\xbf" + "旧行\r\n".encode())
        self.store.select(self.store.current.name)
        self.store.save_document(self.store.text + "新行")
        self.assertTrue(self.store.current.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.store.current.read_text(encoding="utf-8-sig"), "旧行\n新行\n")

    def test_external_edit_never_overwritten(self):
        self.store.save_document("原先内容")
        original = self.store.current
        original.write_text("其他编辑器内容\n", encoding="utf-8")
        with self.assertRaises(ExternalEditError):
            self.store.save_document("原先新增内容")
        recovery = self.store.recover_conflict("原先新增内容")
        self.assertEqual(original.read_text(encoding="utf-8"), "其他编辑器内容\n")
        self.assertEqual(recovery.read_text(encoding="utf-8"), "原先新增内容\n")

    def test_failed_replace_leaves_previous_snapshot(self):
        self.store.save_document("历史")
        with patch("tinynote.storage.os.replace", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                self.store.save_document("新历史")
        self.assertEqual(self.contents(), "历史\n")
        self.assertEqual(self.store.text, "历史")
        self.assertEqual(list(self.root.glob(".tinynote-*.tmp")), [])

    def test_external_edit_refreshes_if_no_local_changes(self):
        self.store.save_document("历史")
        self.store.current.write_text("外部改过的历史\n", encoding="utf-8")
        self.assertEqual(self.store.save_document("历史"), "外部改过的历史\n")

    def test_file_selection_and_exclusive_creation(self):
        self.store.save_document("随手记")
        self.store.select("灵感.md")
        self.store.save_document("灵感")
        self.assertEqual(self.contents(), "灵感\n")
        with self.assertRaises(FileExistsError):
            self.store.create("灵感.md")

    def test_unsafe_names_rejected(self):
        for name in ("../a", "C:\\notes", "nul", "CON.txt", "a/b", "a?", "", "a .md", "LPT1"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                note_name(name)

    def test_unicode_multiline_and_markdown_preserved(self):
        self.store.save_document("# 标题\n- 列表\n🙂 **加粗**")
        self.assertEqual(self.contents(), "# 标题\n- 列表\n🙂 **加粗**\n")

    def test_external_delete_recovers_full_edited_document(self):
        self.store.save_document("原先内容")
        self.store.current.unlink()
        with self.assertRaises(ExternalEditError):
            self.store.save_document("原先新增内容")
        self.store.recover_conflict("原先新增内容")
        self.assertEqual(self.contents(), "原先新增内容\n")


if __name__ == "__main__":
    unittest.main()

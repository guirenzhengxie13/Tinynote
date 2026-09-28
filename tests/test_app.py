import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tinynote.app import NoteWindow
from tinynote.config import load_config
from tinynote.hotkey import ChordFilter, parse_hotkey
from tinynote.storage import NoteStore

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = load_config(self.root)
        self.config["hide_on_blur"] = False
        self.window = NoteWindow(self.root, self.config, NoteStore(self.root / "notes", self.config["default_files"]), False)
        self.editor = self.window.editor

    def tearDown(self):
        for timer in (self.window.save_timer, self.window.idle_timer):
            timer.stop()
        self.window.hide()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, 0)
        self.temp.cleanup()

    def ime(self, commit="", preedit=""):
        event = QInputMethodEvent(preedit, [])
        event.setCommitString(commit)
        QCoreApplication.sendEvent(self.editor, event)

    def contents(self):
        return self.window.store.current.read_text(encoding="utf-8")

    def test_ime_segments_stay_on_same_line_until_period(self):
        self.ime(preedit="zhong")
        self.assertEqual(self.contents(), "")
        self.ime("中文")
        self.assertEqual(self.contents(), "中文\n")
        self.ime("输入")
        self.assertEqual(self.contents(), "中文输入\n")
        self.ime("。")
        self.assertEqual(self.editor.toPlainText(), "中文输入。\n")
        self.ime("下一句")
        self.assertEqual(self.contents(), "中文输入。\n下一句\n")

    def test_multiple_sentences_in_single_commit(self):
        self.ime("第一句。第二句。第三句")
        self.assertEqual(self.contents(), "第一句。\n第二句。\n第三句\n")
        self.assertEqual(self.editor.toPlainText(), "第一句。\n第二句。\n第三句")

    def test_commit_with_new_preedit_is_saved_without_disrupting_ime(self):
        self.ime("完整句。", "xia")
        self.assertTrue(self.editor.composing)
        self.assertEqual(self.contents(), "完整句。\n")
        self.ime("下句")
        self.assertEqual(self.contents(), "完整句。\n下句\n")

    def test_cancel_preedit_does_not_save_pinyin(self):
        self.ime(preedit="nihao")
        self.ime()
        self.assertEqual(self.contents(), "")

    def test_english_period_does_not_split(self):
        QTest.keyClicks(self.editor, "example.com 3.14")
        self.window.process_draft()
        self.assertEqual(self.contents(), "example.com 3.14\n")

    def test_tab_flushes_and_switches_without_inserting_tab(self):
        self.ime("第一份")
        first = self.window.store.current
        QTest.keyClick(self.editor, Qt.Key.Key_Tab)
        self.assertEqual(self.window.store.current.name, "灵感.md")
        self.ime("第二份")
        self.assertEqual(first.read_text(encoding="utf-8"), "第一份\n")
        self.assertEqual(self.contents(), "第二份\n")
        QTest.keyClick(self.editor, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.window.store.current.name, "随手记.md")

    def test_return_commits_and_clears_only_current_line(self):
        self.ime("一行")
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.assertEqual(self.editor.toPlainText(), "一行\n")
        self.ime("下一行")
        self.assertEqual(self.contents(), "一行\n下一行\n")

    def test_left_moves_real_cursor_and_shows_only_four_characters(self):
        self.ime("今天去公园散步")
        QTest.keyClick(self.editor, Qt.Key.Key_Left)
        self.assertTrue(self.editor.revealed)
        self.assertEqual(self.editor.textCursor().position(), 6)
        self.assertEqual(self.editor.visible_context(), "去公园散")
        self.ime("慢")
        self.assertEqual(self.contents(), "今天去公园散慢步\n")
        self.assertEqual(self.editor.visible_context(), "公园散慢")
        self.assertTrue(self.editor.revealed)
        QTest.keyClick(self.editor, Qt.Key.Key_Right)
        self.assertEqual(self.editor.textCursor().position(), 8)
        self.assertFalse(self.editor.revealed)
        self.assertEqual(self.editor.visible_context(), "")

    def test_left_can_edit_previous_saved_line(self):
        self.ime("第一行。第二行。")
        for _ in range(3):
            QTest.keyClick(self.editor, Qt.Key.Key_Left)
        self.ime("新")
        self.assertEqual(self.contents(), "第一行。\n第二新行。\n")
        self.assertEqual(self.editor.visible_context(), "第二新")

    def test_repeated_left_then_right_does_not_change_text(self):
        self.ime("一二三四五六")
        for _ in range(3):
            QTest.keyClick(self.editor, Qt.Key.Key_Left)
        self.assertEqual(self.editor.visible_context(), "一二三")
        for _ in range(3):
            QTest.keyClick(self.editor, Qt.Key.Key_Right)
        self.assertFalse(self.editor.revealed)
        self.assertEqual(self.editor.textCursor().position(), 6)
        self.assertEqual(self.contents(), "一二三四五六\n")

    def test_transparent_single_line_and_focus_loss_hides(self):
        self.assertEqual((self.window.width(), self.window.height()), (320, 34))
        self.assertFalse(hasattr(self.window, "review"))
        self.ime("已有文字")
        self.editor.move_cursor(-1)
        from PySide6.QtCore import QEvent
        APP.sendEvent(self.window, QEvent(QEvent.Type.WindowDeactivate))
        self.assertFalse(self.editor.revealed)

    def test_punctuation_inserted_in_middle_keeps_suffix_and_cursor(self):
        self.ime("甲乙丙丁")
        self.editor.move_cursor(-1)
        self.editor.move_cursor(-1)
        self.ime("。")
        self.assertEqual(self.contents(), "甲乙。\n丙丁\n")
        self.ime("新")
        self.assertEqual(self.contents(), "甲乙。\n新丙丁\n")

    def test_existing_file_load_and_edit_preserves_other_lines(self):
        self.window.store.create("历史.md").write_text("原来一行。\n最后一行\n", encoding="utf-8")
        self.window.select_file("历史.md")
        self.editor.move_cursor(-1)
        self.editor.move_cursor(-1)
        self.ime("新")
        self.assertEqual(self.contents(), "原来一行。\n最后一新行\n")

    def test_emoji_cursor_positions_do_not_split_unicode(self):
        self.ime("甲乙🙂丙丁")
        self.editor.move_cursor(-1)
        self.assertEqual(self.editor.visible_context(), "甲乙🙂丙")
        self.ime("新")
        self.assertEqual(self.contents(), "甲乙🙂丙新丁\n")

    def test_chinese_preedit_does_not_move_cursor_or_change_reveal_mode(self):
        self.ime("甲乙丙")
        self.editor.move_cursor(-1)
        position = self.editor.textCursor().position()
        self.ime(preedit="xin")
        self.editor.move_cursor(1)
        self.assertEqual(self.editor.textCursor().position(), position)
        self.assertTrue(self.editor.revealed)
        self.ime("新")
        self.assertEqual(self.contents(), "甲乙新丙\n")

    def test_delete_and_undo_in_revealed_mode(self):
        self.ime("甲乙丙丁")
        self.editor.move_cursor(-1)
        QTest.keyClick(self.editor, Qt.Key.Key_Backspace)
        self.window.process_draft()
        self.assertEqual(self.contents(), "甲乙丁\n")
        QTest.keyClick(self.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.window.process_draft()
        self.assertEqual(self.contents(), "甲乙丙丁\n")
        self.assertTrue(self.editor.revealed)

    def test_editor_pixels_do_not_reveal_committed_or_preedit_text(self):
        self.window.show()
        APP.processEvents()
        blank = self.editor.viewport().grab().toImage()
        self.ime("这是不能在界面显示的内容")
        self.ime(preedit="pinyin")
        self.editor.selectAll()
        APP.processEvents()
        hidden = self.editor.viewport().grab().toImage()
        self.assertEqual(blank, hidden)

    def test_save_failure_prevents_switch_hide_or_quit(self):
        self.editor.insertPlainText("不能丢失")
        original = self.window.store.current
        with patch("tinynote.storage.atomic_write", side_effect=PermissionError):
            self.assertFalse(self.window.flush())
            self.window.switch_file(1)
            self.assertEqual(original, self.window.store.current)
            self.assertFalse(self.window.hide_note())
            self.assertEqual(self.editor.toPlainText(), "不能丢失")
        self.assertTrue(self.window.flush())
        self.assertEqual(self.contents(), "不能丢失\n")

    def test_external_edit_recovery_in_ui(self):
        self.ime("旧输入")
        original = self.window.store.current
        original.write_text("外部内容", encoding="utf-8")
        self.ime("新输入")
        self.assertEqual(original.read_text(encoding="utf-8"), "外部内容")
        self.assertTrue(self.window.store.current.name.startswith("恢复-"))
        self.assertEqual(self.contents(), "旧输入新输入\n")

    def test_manual_mode_preserves_chinese_period(self):
        self.window.config["newline_mode"] = "manual"
        self.ime("一句。再一句")
        self.assertEqual(self.contents(), "一句。再一句\n")

    def test_no_accidental_copy_to_clipboard(self):
        APP.clipboard().setText("原有剪贴板")
        self.ime("隐藏内容")
        self.editor.selectAll()
        QTest.keyClick(self.editor, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(APP.clipboard().text(), "原有剪贴板")

    def test_extension_command_and_error_isolation(self):
        self.window.api.load(["plugins.timestamp"])
        self.window.run_command("timestamp")
        self.assertRegex(self.editor.toPlainText(), r"\d{4}-\d{2}-\d{2}")
        self.window.api.on("saved", lambda **kwargs: 1 / 0)
        self.assertTrue(self.window.commit())

    def test_global_hotkey_default(self):
        self.assertEqual(self.config["global_hotkey"], "Ctrl+Alt+A")
        self.assertEqual(parse_hotkey("Ctrl+Alt+A"), (0x4003, 0x41))
        with self.assertRaises(ValueError):
            parse_hotkey("Alt")

    def test_fallback_chord_filter_does_not_capture_other_typing(self):
        detector = ChordFilter(0x41, 1)
        self.assertEqual(detector.feed(0x41, True, 0), 0)
        self.assertEqual(detector.feed(0x42, True, 1), 0)
        self.assertEqual(detector.feed(0x41, True, 3), 0)
        self.assertEqual(detector.feed(0x41, True, 1), 2)
        self.assertEqual(detector.feed(0x41, True, 1), 1)
        self.assertEqual(detector.feed(0x41, False, 0), 1)
        self.assertEqual(detector.feed(0x41, True, 1), 2)


if __name__ == "__main__":
    unittest.main()

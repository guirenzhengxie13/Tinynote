from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QEvent, QLockFile, QPoint, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox,
    QPushButton, QSpinBox, QSystemTrayIcon, QWidget)

from .config import load_config
from .editor import HiddenEditor
from .extensions import ExtensionAPI
from .hotkey import GlobalHotkeys
from .instance import InstanceServer, send_command
from .storage import ExternalEditError, NoteStore, atomic_write


def make_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#172725"))
    painter.drawRoundedRect(2, 2, 60, 60, 17, 17)
    painter.setPen(QPen(QColor("#b9ddc8"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(19, 21, 45, 21)
    painter.drawLine(32, 21, 32, 44)
    painter.end()
    return QIcon(pixmap)


class NoteWindow(QWidget):
    def __init__(self, root: Path, config: dict, store: NoteStore, tray_enabled=True):
        super().__init__()
        self.root, self.config, self.store = root, config, store
        self.busy = 0
        self.save_failed = False
        self.previous_window = None
        self.drag_start = None
        self.setWindowTitle("TinyNote · 隐蔽速记")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(config["window_width"], 34)
        self.setWindowIcon(make_icon())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(7)
        self.file_button = QPushButton()
        self.file_button.setFixedWidth(64)
        self.file_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_button.clicked.connect(self.file_menu)
        self.file_button.setStyleSheet("QPushButton {color: rgba(170,200,185,170); background: transparent; border: none; padding: 0; font-size: 10px;}")
        layout.addWidget(self.file_button)
        self.editor = HiddenEditor()
        self.editor.replace_document(store.text)
        self.normalized_text = store.text
        layout.addWidget(self.editor, 1)
        self.status = QLabel("·")
        self.status.setFixedWidth(10)
        self.status.setStyleSheet("color: #86b39c; background: transparent;")
        self.status.setToolTip("内容隐藏 · 左右键显示上下文 · Ctrl+H 隐藏文字")
        layout.addWidget(self.status)

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.process_draft)
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self.commit)
        self.editor.textChanged.connect(self.text_changed)
        self.editor.ime_committed.connect(self.ime_committed)
        self.editor.composition_changed.connect(self.composition_changed)
        self.editor.mode_changed.connect(lambda shown: self.set_status("光标编辑" if shown else "内容隐藏"))

        self.api = ExtensionAPI(self)
        self.register_commands()
        self.tray = QSystemTrayIcon(self.windowIcon(), self) if tray_enabled else None
        if self.tray:
            self.tray.setToolTip("TinyNote · " + config["global_hotkey"])
            self.tray.activated.connect(lambda reason: self.toggle() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            menu = QMenu()
            for title, callback in (("唤出 / 收起", self.toggle), ("打开笔记目录", self.open_folder),
                                    ("设置", self.settings), ("快捷键", self.help), ("退出", self.quit)):
                menu.addAction(title, callback)
            self.tray.setContextMenu(menu)
            self.tray.show()
        self.api.load(config["plugins"])
        self.bindings = {}
        for command in self.api.commands.values():
            shortcut = config["shortcuts"].get(command.id, command.shortcut)
            if shortcut:
                canonical = QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.PortableText)
                if not canonical or canonical in self.bindings:
                    raise ValueError(f"快捷键无效或重复：{shortcut}")
                command.shortcut = canonical
                self.bindings[canonical] = command.id
        self.editor.dispatch = self.dispatch
        self.editor.conceal_shortcut = self.api.commands["conceal"].shortcut
        self.refresh_file()

    def register_commands(self):
        for key, title, callback in (
            ("next_file", "下一份笔记", lambda: self.switch_file(1)),
            ("previous_file", "上一份笔记", lambda: self.switch_file(-1)),
            ("commit", "保存并换行", self.commit), ("hide", "保存并收起", self.hide_note),
            ("review_previous", "光标左移，显示上下文", lambda: self.editor.move_cursor(-1)),
            ("review_next", "光标右移，显示上下文", lambda: self.editor.move_cursor(1)),
            ("conceal", "隐藏文字，保留光标位置", self.conceal_review),
            ("new_file", "新建 Markdown", self.new_file), ("open_folder", "打开笔记目录", self.open_folder),
            ("open_file", "打开当前 Markdown", self.open_file), ("commands", "全部命令", self.command_menu),
            ("settings", "偏好设置", self.settings), ("help", "快捷键帮助", self.help),
            ("opacity", "切换透明度", self.cycle_opacity), ("quit", "保存并退出", self.quit)):
            self.api.register_command(key, title, callback, self.config["shortcuts"].get(key, ""))

    def dispatch(self, sequence):
        if sequence == "Shift+Backtab":
            sequence = "Shift+Tab"
        command_id = self.bindings.get(sequence)
        if command_id:
            self.run_command(command_id)
            return True
        if re.fullmatch(r"Ctrl\+[1-9]", sequence):
            files = self.store.files()
            index = int(sequence[-1]) - 1
            if index < len(files):
                self.select_file(files[index].name)
            return True
        return False

    def run_command(self, command_id):
        try:
            self.api.commands[command_id].callback()
        except Exception:
            self.notify("命令执行失败", "当前输入仍保留在速记框中，请检查设置或扩展。")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(205, 232, 218, 44), 1))
        painter.setBrush(QColor(15, 28, 23, round(self.config["opacity"] * 255)))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_start)

    def mouseReleaseEvent(self, event):
        self.drag_start = None

    def set_status(self, message):
        self.status.setText("!" if self.save_failed else ("‹" if self.editor.revealed else "·"))
        self.status.setToolTip(message)

    def notify(self, title, message):
        if self.tray:
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Warning, 4000)
        self.set_status(title)

    def refresh_file(self):
        self.file_button.setText(self.file_button.fontMetrics().elidedText(self.store.current.stem, Qt.TextElideMode.ElideRight, 58))
        self.file_button.setToolTip(str(self.store.current))

    def text_changed(self):
        if self.editor.in_ime_event:
            return
        self.set_status("正在保存…")
        self.save_timer.start(self.config["autosave_ms"])
        if self.config["newline_mode"] == "idle" and not self.editor.composing:
            self.idle_timer.start(self.config["idle_ms"])

    def composition_changed(self, composing):
        if composing:
            self.idle_timer.stop()

    def ime_committed(self):
        self.process_draft()  # IME commits are persisted synchronously.
        if self.config["newline_mode"] == "ime" and not self.editor.composing:
            self.commit()
        elif self.config["newline_mode"] == "idle" and not self.editor.composing:
            self.idle_timer.start(self.config["idle_ms"])

    def persist(self, text, commit=False):
        try:
            try:
                saved = self.store.save_document(text)
            except ExternalEditError:
                self.store.recover_conflict(text)
                saved = text
                self.refresh_file()
                self.notify("已保存到恢复文件", "原文件已被外部修改；编辑后的完整笔记已另存为恢复 Markdown。")
            if saved != text:
                self.editor.replace_document(saved, self.editor.textCursor().position())
                self.normalized_text = saved
            self.save_failed = False
            self.set_status("已保存 · 光标编辑" if self.editor.revealed else "已保存 · 内容隐藏")
            self.api.emit("saved", path=self.store.current, text=saved, committed=commit)
            return True
        except (OSError, UnicodeError) as exc:
            if not self.save_failed:
                self.notify("保存失败 · 输入仍保留", f"请检查笔记目录权限或磁盘空间（{type(exc).__name__}）。")
            self.save_failed = True
            self.set_status("保存失败 · 输入仍保留，请勿关闭")
            return False

    def process_draft(self):
        self.save_timer.stop()
        # Normalize only newly inserted periods, preserving the insertion point
        # and any text after it. QTextCursor handles UTF-16 positions for us.
        if self.config["newline_mode"] == "punctuation" and not self.editor.composing:
            self.normalize_periods()
        return self.persist(self.editor.toPlainText())

    def normalize_periods(self):
        text = self.editor.toPlainText()
        previous = self.normalized_text
        start = 0
        while start < min(len(text), len(previous)) and text[start] == previous[start]:
            start += 1
        end, old_end = len(text), len(previous)
        while end > start and old_end > start and text[end - 1] == previous[old_end - 1]:
            end -= 1
            old_end -= 1
        positions = [i + 1 for i in range(start, end) if text[i] == "。" and (i + 1 == len(text) or text[i + 1] != "\n")]
        if not positions:
            self.normalized_text = text
            return
        live_cursor = self.editor.textCursor()
        was_blocked = self.editor.blockSignals(True)
        edit_cursor = QTextCursor(self.editor.document())
        edit_cursor.beginEditBlock()
        try:
            for position in reversed(positions):
                edit_cursor.setPosition(len(text[:position].encode("utf-16-le")) // 2)
                edit_cursor.insertText("\n")
        finally:
            edit_cursor.endEditBlock()
            self.editor.setTextCursor(live_cursor)
            self.editor.blockSignals(was_blocked)
        self.normalized_text = self.editor.toPlainText()

    def finish_composition(self):
        if self.editor.composing:
            QApplication.inputMethod().commit()

    def flush(self):
        self.finish_composition()
        self.save_timer.stop()
        self.idle_timer.stop()
        if self.editor.composing:
            return False
        return self.process_draft()

    def commit(self):
        if not self.flush():
            return False
        self.editor.insertPlainText("\n")
        self.save_timer.stop()
        self.idle_timer.stop()
        return self.persist(self.editor.toPlainText(), commit=True)

    def select_file(self, name):
        if not self.flush():
            return
        try:
            self.store.select(name)
        except (OSError, UnicodeError, ValueError):
            self.notify("无法打开笔记", "请检查文件是否存在、可读且为 UTF-8 编码。")
            return
        self.editor.replace_document(self.store.text)
        self.normalized_text = self.store.text
        self.conceal_review()
        self.refresh_file()
        self.set_status("已切换 · " + self.store.current.stem)
        self.api.emit("file_changed", path=self.store.current)
        self.editor.setFocus()

    def switch_file(self, step):
        files = self.store.files()
        if files:
            index = next((i for i, p in enumerate(files) if p == self.store.current), 0)
            self.select_file(files[(index + step) % len(files)].name)

    def conceal_review(self):
        self.editor.set_revealed(False)

    def show_note(self):
        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = ctypes.c_void_p
            self.previous_window = user32.GetForegroundWindow()
        if not self.isVisible():
            screen = QApplication.screenAt(self.cursor().pos()) or QApplication.primaryScreen()
            rect = screen.availableGeometry()
            self.move(rect.right() - self.width() - 32, rect.bottom() - self.height() - 48)
        self.conceal_review()
        self.show()
        self.raise_()
        if sys.platform == "win32":
            ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(int(self.winId())))
        self.activateWindow()
        self.editor.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def hide_note(self, restore=True):
        if not self.flush():
            self.conceal_review()
            return False
        self.conceal_review()
        self.hide()
        if restore and self.previous_window and sys.platform == "win32":
            ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(self.previous_window))
        return True

    def toggle(self):
        if self.busy:
            return
        if self.isVisible():
            self.hide_note()
        else:
            self.show_note()

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate and hasattr(self, "config"):
            self.conceal_review()
            if self.config["hide_on_blur"] and not self.busy:
                QTimer.singleShot(0, self.hide_if_inactive)
        return super().event(event)

    def hide_if_inactive(self):
        if self.isVisible() and not self.isActiveWindow() and not self.busy:
            self.hide_note(restore=False)

    @contextmanager
    def dialog_guard(self):
        self.busy += 1
        self.conceal_review()
        try:
            yield
        finally:
            self.busy -= 1
            if self.isVisible():
                self.activateWindow()
                self.editor.setFocus()

    def file_menu(self):
        with self.dialog_guard():
            menu = QMenu(self)
            for index, path in enumerate(self.store.files()):
                action = menu.addAction(f"{index + 1:02d}   {path.stem}")
                action.triggered.connect(lambda checked=False, name=path.name: self.select_file(name))
            menu.addSeparator()
            menu.addAction("新建笔记…", self.new_file)
            menu.exec(self.file_button.mapToGlobal(QPoint(0, self.file_button.height())))

    def command_menu(self):
        with self.dialog_guard():
            menu = QMenu(self)
            for command in self.api.commands.values():
                action = menu.addAction(command.title + "\t" + command.shortcut)
                action.triggered.connect(lambda checked=False, cid=command.id: self.run_command(cid))
            menu.exec(self.mapToGlobal(QPoint(20, 40)))

    def new_file(self):
        with self.dialog_guard():
            name, ok = QInputDialog.getText(self, "新建笔记", "Markdown 文件名：")
            if ok and name.strip():
                try:
                    path = self.store.create(name)
                    self.select_file(path.name)
                except (OSError, ValueError) as exc:
                    QMessageBox.warning(self, "无法新建", str(exc))

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.directory)))

    def open_file(self):
        if self.flush():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.current)))

    def cycle_opacity(self):
        levels = (0.0, 0.03, 0.08, 0.15)
        self.config["opacity"] = next((value for value in levels if value > self.config["opacity"] + 0.01), levels[0])
        self.update()
        self.set_status(f"背景不透明度 {self.config['opacity']:.0%} · 设置中可保存")

    def settings(self):
        with self.dialog_guard():
            dialog = QDialog(self)
            dialog.setWindowTitle("TinyNote · 设置")
            layout = QFormLayout(dialog)
            mode = QComboBox()
            for title, value in (("遇到中文句号 。 换行", "punctuation"), ("停顿后换行", "idle"),
                                 ("每次输入法确认换行", "ime"), ("仅 Enter 换行", "manual")):
                mode.addItem(title, value)
            mode.setCurrentIndex(mode.findData(self.config["newline_mode"]))
            layout.addRow("自动换行", mode)
            opacity = QSpinBox()
            opacity.setRange(0, 100)
            opacity.setSuffix(" %")
            opacity.setValue(round(self.config["opacity"] * 100))
            layout.addRow("背景不透明度", opacity)
            layout.addRow(QLabel("更多快捷键、目录与扩展：config.json（重启生效）"))
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addRow(buttons)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                updated = self.config | {"newline_mode": mode.currentData(), "opacity": opacity.value() / 100}
                try:
                    atomic_write(self.root / "config.json", (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
                    self.config = updated
                    self.idle_timer.stop()
                    self.update()
                except OSError:
                    QMessageBox.warning(self, "保存失败", "无法写入 config.json，设置未变更。")

    def help(self):
        with self.dialog_guard():
            rows = [f"{self.config['global_hotkey']}   唤出 / 收起（全局）", "Ctrl+1…9   直接切换笔记"]
            rows += [f"{c.shortcut or '命令菜单'}   {c.title}" for c in self.api.commands.values()]
            QMessageBox.information(self, "TinyNote · 快捷键", "\n".join(rows) + "\n\n中文选词确认后保存；默认遇到 。 换行。\n输入法候选窗由系统控制，可能仍然可见。")

    def quit(self):
        if self.flush():
            if self.tray:
                self.tray.hide()
            QApplication.instance().quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide_note()


def main(argv=None):
    parser = argparse.ArgumentParser(description="TinyNote · 隐蔽速记")
    parser.add_argument("--show", action="store_true", help="启动后直接显示输入框")
    parser.add_argument("--data-dir", type=Path, help="配置与笔记所在目录")
    parser.add_argument("--quit", action="store_true", help="保存并退出已经运行的实例")
    parser.add_argument("--startup-token", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.data_dir or (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("TinyNote")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setQuitOnLastWindowClosed(False)
    root.mkdir(parents=True, exist_ok=True)
    runtime = root / ".runtime"
    runtime.mkdir(exist_ok=True)
    def report_startup(ok, message=""):
        if args.startup_token and re.fullmatch(r"[0-9a-f]{32}", args.startup_token):
            atomic_write(runtime / f"launch-{args.startup_token}.json", json.dumps({"ok": ok, "message": message}).encode())

    if args.quit:
        closed = send_command(root, "quit")
        report_startup(closed, "Unable to close the existing TinyNote instance.")
        return 0 if closed else 1
    lock = QLockFile(str(runtime / "tinynote.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        shown = send_command(root, "show")
        report_startup(shown, "An older TinyNote is running. Exit it from the tray, then run start.cmd again.")
        if not shown and not args.startup_token:
            QMessageBox.information(None, "TinyNote", "旧版程序仍在运行，请先从托盘退出旧版，再重新启动。")
        return 0 if shown else 1
    try:
        config = load_config(root)
        hotkeys = GlobalHotkeys(config["global_hotkey"], config["hotkey_fallback"])
        directory = Path(config["notes_dir"])
        store = NoteStore(directory if directory.is_absolute() else root / directory, config["default_files"])
        window = NoteWindow(root, config, store)
        instance_server = InstanceServer(root, window)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        report_startup(False, str(exc))
        if not args.startup_token:
            QMessageBox.critical(None, "TinyNote · 启动失败", str(exc))
        lock.unlock()
        return 1
    hotkeys.activated.connect(window.toggle)
    hotkeys.problem.connect(lambda message: window.notify("热键不可用", message))
    app.aboutToQuit.connect(hotkeys.stop)
    app.commitDataRequest.connect(lambda manager: None if window.flush() else manager.cancel())
    hotkeys.start()
    if args.show or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show_note()
    else:
        window.tray.showMessage("TinyNote 已就绪", f"按 {config['global_hotkey']} 开始速记，右键托盘可设置或退出。", QSystemTrayIcon.MessageIcon.Information, 2500)
    report_startup(True)
    try:
        return app.exec()
    finally:
        hotkeys.stop()
        lock.unlock()

"""Explicit opt-in extension API: commands and events, isolated failures."""
from dataclasses import dataclass
from collections import defaultdict
import importlib
from typing import Callable


@dataclass
class Command:
    id: str
    title: str
    callback: Callable
    shortcut: str = ""


class ExtensionAPI:
    def __init__(self, window):
        self.window = window
        self.commands: dict[str, Command] = {}
        self.listeners = defaultdict(list)

    def register_command(self, command_id, title, callback, shortcut=""):
        if command_id in self.commands:
            raise ValueError(f"命令已存在：{command_id}")
        self.commands[command_id] = Command(command_id, title, callback, shortcut)

    def on(self, event, callback):
        self.listeners[event].append(callback)

    def emit(self, event, **payload):
        for callback in self.listeners[event]:
            try:
                callback(**payload)
            except Exception:
                self.window.notify("扩展执行失败", "请检查扩展代码；笔记已保留。")

    def insert_text(self, text: str):
        self.window.editor.insertPlainText(text)

    @property
    def current_path(self):
        return self.window.store.current

    def load(self, modules):
        for module in modules:
            try:
                importlib.import_module(module).setup(self)
            except Exception:
                self.window.notify("扩展加载失败", f"无法加载 {module}")

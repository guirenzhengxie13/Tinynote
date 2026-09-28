"""A Windows hotkey with an optional chord-only hook for occupied shortcuts."""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from PySide6.QtCore import QObject, Signal


def parse_hotkey(value: str) -> tuple[int, int]:
    parts = value.upper().replace(" ", "").split("+")
    modifiers = {"ALT": 1, "CTRL": 2, "CONTROL": 2, "SHIFT": 4, "WIN": 8}
    if len(parts) < 2 or len(parts[-1]) != 1 or not parts[-1].isascii() or not parts[-1].isalnum():
        raise ValueError("全局热键格式示例：Alt+A、Ctrl+Alt+N")
    mask = 0x4000  # MOD_NOREPEAT
    for part in parts[:-1]:
        if part not in modifiers:
            raise ValueError(f"不支持的修饰键：{part}")
        mask |= modifiers[part]
    return mask, ord(parts[-1])


class GlobalHotkeys(QObject):
    activated = Signal()
    problem = Signal(str)
    ready = Signal(bool)

    def __init__(self, chord: str, allow_fallback: bool = True):
        super().__init__()
        self.chord = chord
        self.allow_fallback = allow_fallback
        self.backend = "unavailable"
        self.modifiers, self.vk = parse_hotkey(chord)
        self.thread_id = 0
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self):
        if sys.platform != "win32":
            self.problem.emit("当前系统不支持全局热键，请使用托盘入口")
            return
        self.thread = threading.Thread(target=self._run, name="tinynote-hotkey", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        if self.thread:
            self.thread.join(timeout=2)

    def _run(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        registered = bool(user32.RegisterHotKey(None, 1, self.modifiers, self.vk))
        hook = None
        if registered:
            self.backend = "registered"
        elif self.allow_fallback:
            hook = self._install_hook(user32, kernel32)
            if hook:
                self.backend = "hook"
        self.ready.emit(bool(registered or hook))
        if not registered and not hook:
            self.problem.emit(f"{self.chord} 无法启用。请使用托盘入口并修改 config.json。")
            return
        try:
            while not self.stop_event.is_set() and user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:
                    self.activated.emit()
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            if registered:
                user32.UnregisterHotKey(None, 1)
            if hook:
                user32.UnhookWindowsHookEx(hook)

    def _install_hook(self, user32, kernel32):
        result_type = ctypes.c_ssize_t
        callback_type = ctypes.WINFUNCTYPE(result_type, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KeyboardData(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HANDLE
        user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = result_type
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        self.filter = ChordFilter(self.vk, self.modifiers & 0xF)

        def callback(code, wparam, lparam):
            if code >= 0:
                event = ctypes.cast(lparam, ctypes.POINTER(KeyboardData)).contents
                # Only the configured trigger key is examined; no text,
                # foreground application names, or unrelated key history is kept.
                if event.vkCode == self.vk and not event.flags & 0x10:
                    mask = 0
                    for key, bit in ((0x12, 1), (0x11, 2), (0x10, 4), (0x5B, 8), (0x5C, 8)):
                        if user32.GetAsyncKeyState(key) & 0x8000:
                            mask |= bit
                    result = self.filter.feed(event.vkCode, wparam in (0x100, 0x104), mask)
                    if result == 2:
                        self.activated.emit()
                    if result:
                        return 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        self._callback = callback_type(callback)
        return user32.SetWindowsHookExW(13, self._callback, kernel32.GetModuleHandleW(None), 0)


class ChordFilter:
    """Return 0=pass, 1=consume, 2=consume and activate; suppress repeat."""
    def __init__(self, vk: int, modifiers: int):
        self.vk, self.modifiers = vk, modifiers
        self.pressed = False

    def feed(self, vk: int, down: bool, modifiers: int) -> int:
        if vk != self.vk:
            return 0
        if self.pressed:
            if not down:
                self.pressed = False
            return 1
        if down and modifiers == self.modifiers:
            self.pressed = True
            return 2
        return 0

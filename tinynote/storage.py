"""Live Markdown persistence, with atomic replacement and external-edit detection."""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path


class ExternalEditError(OSError):
    """Another editor changed the target since our last successful write."""


def note_name(name: str) -> str:
    name = name.strip()
    if not name.lower().endswith(".md"):
        name += ".md"
    if (len(name) > 120 or name in (".md", "..md") or
            re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or
            name[:-3].endswith((".", " ")) or
            name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}):
        raise ValueError("请输入有效的 Markdown 文件名，不要包含路径或特殊字符")
    return name


def atomic_write(path: Path, data: bytes, expected: bytes | None = None) -> None:
    fd, temp = tempfile.mkstemp(prefix=".tinynote-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Check again immediately before replacement. This protects ordinary
        # external edits; arbitrary third-party writes cannot be locked by us.
        if expected is not None and (not path.exists() or path.read_bytes() != expected):
            raise ExternalEditError("文件被其他程序修改")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class NoteStore:
    """An editable document snapshot; concurrent changes never get overwritten."""
    def __init__(self, directory: Path, defaults: list[str]):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.defaults = [note_name(n) for n in defaults]
        for name in self.defaults:
            (self.directory / name).touch(exist_ok=True)
        self.current = self.directory / self.defaults[0]
        self.expected = b""
        self.text = ""
        self.select(self.current.name)

    def files(self) -> list[Path]:
        order = {name: i for i, name in enumerate(self.defaults)}
        return sorted((p for p in self.directory.glob("*.md") if p.is_file()),
                      key=lambda p: (order.get(p.name, len(order)), p.name.casefold()))

    def select(self, name: str) -> None:
        path = self.directory / note_name(name)
        data = path.read_bytes()
        text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        self.current, self.expected, self.text = path, data, text

    def create(self, name: str) -> Path:
        path = self.directory / note_name(name)
        with path.open("x", encoding="utf-8"):
            pass
        return path

    def save_document(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        try:
            latest = self.current.read_bytes()
        except FileNotFoundError as exc:
            raise ExternalEditError("文件被其他程序移动或删除") from exc
        if latest != self.expected:
            if text != self.text:
                raise ExternalEditError("文件被其他程序修改")
            self.select(self.current.name)
            return self.text
        if text == self.text:
            return text
        payload = (text + ("\n" if text and not text.endswith("\n") else "")).encode("utf-8")
        if self.expected.startswith(b"\xef\xbb\xbf"):
            payload = b"\xef\xbb\xbf" + payload
        atomic_write(self.current, payload, self.expected)
        self.expected, self.text = payload, text
        return text

    def recover_conflict(self, text: str) -> Path:
        path = self.create(f"恢复-{datetime.now():%Y%m%d-%H%M%S-%f}.md")
        state = self.current, self.expected, self.text
        try:
            self.select(path.name)
            self.save_document(text)
        except Exception:
            self.current, self.expected, self.text = state
            raise
        return path

from __future__ import annotations

import json
from pathlib import Path

DEFAULTS = {
    "notes_dir": "notes",
    "default_files": ["随手记.md", "灵感.md", "待办.md"],
    "newline_mode": "punctuation",
    "idle_ms": 1200,
    "autosave_ms": 180,
    "opacity": 0.03,
    "window_width": 320,
    "hide_on_blur": True,
    "global_hotkey": "Ctrl+Alt+A",
    "hotkey_fallback": True,
    "shortcuts": {
        "next_file": "Tab", "previous_file": "Shift+Tab",
        "commit": "Return", "hide": "Esc", "conceal": "Ctrl+H",
        "review_previous": "Left", "review_next": "Right",
        "new_file": "Ctrl+N", "open_folder": "Ctrl+O",
        "open_file": "Ctrl+Shift+O", "commands": "Ctrl+K",
        "settings": "Ctrl+,", "help": "F1",
        "opacity": "F2", "quit": "Ctrl+Q",
    },
    "plugins": [],
}


def load_config(root: Path) -> dict:
    path = root / "config.json"
    if not path.exists():
        path.write_text(json.dumps(DEFAULTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    supplied = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(supplied, dict):
        raise ValueError("config.json 必须是 JSON 对象")
    config = DEFAULTS | supplied
    config.pop("context_chars", None)  # Older settings no longer limit context.
    if not isinstance(config["shortcuts"], dict):
        raise ValueError("shortcuts 必须是 JSON 对象")
    config["shortcuts"] = DEFAULTS["shortcuts"] | config["shortcuts"]
    if config["newline_mode"] not in ("punctuation", "idle", "ime", "manual"):
        raise ValueError("newline_mode 必须是 punctuation、idle、ime 或 manual")
    for key, low, high in (("idle_ms", 300, 60000), ("autosave_ms", 30, 5000),
                           ("window_width", 200, 800)):
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError(f"{key} 必须是 {low}–{high} 之间的整数")
    if type(config["opacity"]) not in (int, float) or not 0 <= config["opacity"] <= 1:
        raise ValueError("opacity 必须在 0–1 之间")
    for key in ("hide_on_blur", "hotkey_fallback"):
        if type(config[key]) is not bool:
            raise ValueError(f"{key} 必须是 true 或 false")
    if not isinstance(config["notes_dir"], str) or not config["notes_dir"].strip():
        raise ValueError("notes_dir 必须是目录路径")
    if (not isinstance(config["default_files"], list) or not config["default_files"] or
            not all(isinstance(name, str) for name in config["default_files"])):
        raise ValueError("default_files 必须是非空文件名列表")
    if not isinstance(config["global_hotkey"], str):
        raise ValueError("global_hotkey 必须是热键字符串")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in config["shortcuts"].items()):
        raise ValueError("shortcuts 的键和值必须是字符串")
    if not isinstance(config["plugins"], list) or not all(isinstance(p, str) for p in config["plugins"]):
        raise ValueError("plugins 必须是模块名列表")
    return config

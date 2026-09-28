"""Example: add plugins.timestamp to config.json's plugins list."""
from datetime import datetime


def setup(api):
    api.register_command("timestamp", "插入当前时间", lambda: api.insert_text(datetime.now().strftime("%Y-%m-%d %H:%M ")), "Ctrl+T")

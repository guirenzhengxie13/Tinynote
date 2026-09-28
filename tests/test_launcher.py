"""Exercise the actual Windows .cmd launcher and local instance lifecycle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32", "Windows launcher")
class LauncherTests(unittest.TestCase):
    def test_cmd_from_other_directory_with_spaces_and_unicode(self):
        with tempfile.TemporaryDirectory(prefix="TinyNote 启动 test ") as directory:
            data = Path(directory)
            (data / "config.json").write_text(json.dumps({"global_hotkey": "Ctrl+Alt+Shift+9", "hotkey_fallback": False}), encoding="utf-8")
            environment = os.environ | {"QT_QPA_PLATFORM": "offscreen", "PYTHONUTF8": "1"}
            command = ["cmd.exe", "/d", "/c", str(ROOT / "start.cmd"), "--data-dir", str(data)]
            try:
                first = subprocess.run(command, cwd=data, env=environment, capture_output=True, timeout=25)
                self.assertEqual(first.returncode, 0, first.stdout.decode("utf-8", errors="replace"))
                lock = data / ".runtime" / "tinynote.lock"
                self.assertTrue(lock.exists())
                original_pid = lock.read_text().splitlines()[0]
                second = subprocess.run(command, cwd=data, env=environment, capture_output=True, timeout=25)
                self.assertEqual(second.returncode, 0, second.stdout.decode("utf-8", errors="replace"))
                self.assertEqual(lock.read_text().splitlines()[0], original_pid)
                self.assertEqual(list((data / ".runtime").glob("launch-*.json")), [])
            finally:
                stopped = subprocess.run([sys.executable, str(ROOT / "main.py"), "--quit", "--data-dir", str(data)],
                                         cwd=data, env=environment, capture_output=True, timeout=10)
                for _ in range(50):
                    if not (data / ".runtime" / "tinynote.lock").exists():
                        break
                    time.sleep(0.05)
                self.assertEqual(stopped.returncode, 0, stopped.stderr.decode("utf-8", errors="replace"))
                self.assertFalse((data / ".runtime" / "tinynote.lock").exists())
                # The venv's Windows launcher can outlive the GUI process for
                # a moment while still holding its redirected log handle.
                for _ in range(80):
                    try:
                        (data / ".runtime" / "startup.log").unlink(missing_ok=True)
                        break
                    except PermissionError:
                        time.sleep(0.05)

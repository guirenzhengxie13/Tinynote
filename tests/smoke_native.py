"""Opt-in Windows registration/message-loop smoke test (no simulated typing)."""
import ctypes
import sys
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest
from tinynote.hotkey import GlobalHotkeys


def wait_until(predicate):
    for _ in range(100):
        if predicate():
            return
        QTest.qWait(20)
    raise AssertionError("Native hotkey test timed out")


def main():
    if sys.platform != "win32":
        print("SKIP: Windows only")
        return
    app = QCoreApplication([])
    hotkey = GlobalHotkeys("Ctrl+Alt+A")
    ready, triggered = [], []
    hotkey.ready.connect(ready.append)
    hotkey.activated.connect(lambda: triggered.append(True))
    hotkey.start()
    try:
        wait_until(lambda: ready)
        assert ready == [True], "Ctrl+Alt+A registration and compatibility mode are unavailable"
        print("Ctrl+Alt+A backend:", hotkey.backend)
        ctypes.windll.user32.PostThreadMessageW(hotkey.thread_id, 0x0312, 1, 0)
        wait_until(lambda: triggered)
        assert triggered == [True]
    finally:
        hotkey.stop()
    assert not hotkey.thread.is_alive(), "Hotkey thread did not stop"
    again = GlobalHotkeys("Ctrl+Alt+A")
    registered = []
    again.ready.connect(registered.append)
    again.start()
    try:
        wait_until(lambda: registered)
        assert registered == [True], "Hotkey was not released"
    finally:
        again.stop()
    print("PASS: Ctrl+Alt+A setup, dispatch, clean shutdown and repeated setup")


if __name__ == "__main__":
    main()

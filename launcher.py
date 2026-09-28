"""Start the desktop app without a console and report real startup failures."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", type=Path)
    options, _ = parser.parse_known_args()
    runtime = (options.data_dir.resolve() if options.data_dir else root) / ".runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    status_file = runtime / f"launch-{token}.json"
    log_path = runtime / "startup.log"
    executable = Path(sys.executable)
    if os.name == "nt" and executable.with_name("pythonw.exe").exists():
        executable = executable.with_name("pythonw.exe")
    command = [str(executable), "-X", "utf8", str(root / "main.py"), "--show", "--startup-token", token, *sys.argv[1:]]
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    try:
        with log_path.open("ab") as log:
            arguments = dict(cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True)
            # Some terminal hosts put children in a kill-on-close job. Escape
            # it when allowed, and still support ordinary Windows desktops.
            try:
                child = subprocess.Popen(command, creationflags=flags | (0x01000000 if os.name == "nt" else 0), **arguments)
            except OSError:
                child = subprocess.Popen(command, creationflags=flags, **arguments)
        for _ in range(100):
            if status_file.exists():
                status = json.loads(status_file.read_text(encoding="utf-8"))
                status_file.unlink()
                if status["ok"]:
                    return 0
                print(status["message"])
                return 1
            if child.poll() is not None:
                break
            time.sleep(0.1)
        print(f"TinyNote did not confirm startup. See: {log_path}")
        return 1
    except (OSError, ValueError) as exc:
        print(f"Unable to start TinyNote: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

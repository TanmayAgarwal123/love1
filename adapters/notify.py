"""Nudges for YOU only: terminal + local log file + optional desktop popup.

There is no recipient parameter anywhere in this module.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .base import Notifier


class LocalNotifier(Notifier):
    def __init__(self, log_path: Path, desktop: bool = False):
        self.log_path = Path(log_path)
        self.desktop = desktop

    def notify(self, title: str, body: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} NUDGE FOR YOU — {title}: {body}"
        print(line, file=sys.stderr)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.desktop:
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", title, body], check=False)
            elif shutil.which("osascript"):
                subprocess.run(["osascript", "-e", f'display notification "{body}" with title "{title}"'],
                               check=False)


class RecordingNotifier(Notifier):
    """Used by tests and the simulator."""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, body: str) -> None:
        self.sent.append((title, body))

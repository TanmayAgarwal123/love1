"""Single log format for every workflow: one JSON object per line.

Fields: ts, workflow, mode (dry_run|live), kind, trigger (evidence), action
(taken or proposed), status, data.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class EventLog:
    def __init__(self, path: Path):
        self.path = Path(path)

    def write(self, *, ts: datetime, workflow: str, mode: str, kind: str, trigger: str,
              action: str, status: str, data: dict | None = None) -> dict:
        rec = {
            "ts": ts.isoformat(timespec="seconds"),
            "workflow": workflow,
            "mode": mode,
            "kind": kind,
            "trigger": trigger,
            "action": action,
            "status": status,
            "data": data or {},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out


def format_line(rec: dict) -> str:
    tag = "DRY-RUN" if rec.get("mode") == "dry_run" else "LIVE"
    return (f"{rec['ts']} [{tag}] {rec['workflow']}.{rec['kind']} ({rec['status']}) "
            f"— {rec['action']} | evidence: {rec['trigger']}")

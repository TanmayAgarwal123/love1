"""Simulate a full week in dry-run against sample data in a throwaway sandbox."""
from __future__ import annotations

import shutil
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

from adapters.notify import RecordingNotifier

from .config import ROOT, Config
from .context import build_context
from .schedule import due

SAMPLE_OVERRIDES = {
    "dry_run": True,
    "timezone": "America/New_York",
    "messaging": {"channel": "whatsapp", "whatsapp": {
        "export_dir": "imports/whatsapp", "drafts_dir": "imports/drafts",
        "my_name": "Me", "partner_name": "Partner", "date_order": "dmy"}},
    "calendars": {"mine": [{"name": "mine", "ics": "imports/calendars/mine.ics"}],
                  "hers": [{"name": "hers", "ics": "imports/calendars/hers.ics"}]},
    "paths": {"data": "data", "logs": "logs", "reports": "reports"},
    "partner": {"label": "Partner", "birthday": "2000-12-06", "milestones": []},
}


def make_sandbox(path: Path | None = None, overrides: dict | None = None) -> Config:
    sb = Path(path or tempfile.mkdtemp(prefix="relops-sim-"))
    for sub in ("whatsapp", "drafts", "calendars"):
        dst = sb / "imports" / sub
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(ROOT / "samples" / sub, dst)
    from .config import deep_merge
    cfg = Config.load(ROOT / "config.example.yaml", deep_merge(SAMPLE_OVERRIDES, overrides or {}), base_dir=sb)
    for wf in cfg.raw["workflows"].values():
        wf["live"] = False
    return cfg


def simulate_week(start: date = date(2026, 11, 16), sandbox: Path | None = None, step_minutes: int = 5,
                  out=print) -> dict:
    from dashboard import sunday
    from workflows import REGISTRY

    cfg = make_sandbox(sandbox)
    tz = cfg.tz
    now = datetime.combine(start, time(0, 0), tzinfo=tz)
    ctx = build_context(cfg, now=now, notifier=RecordingNotifier())
    end = now + timedelta(days=7)
    runs: dict[str, int] = {}
    report = None
    while now < end:
        ctx.now = now
        for name in due(now):
            if name == "dashboard":
                report = sunday.run(ctx, week_ending=now.date())
            elif cfg.enabled(name):
                REGISTRY[name].run(ctx)
            runs[name] = runs.get(name, 0) + 1
        now += timedelta(minutes=step_minutes)

    records = ctx.log.read()
    data_dir = cfg.path("data")
    real_writes = [p for p in data_dir.rglob("*") if p.is_file() and ".dryrun" not in p.parts] if data_dir.exists() else []
    summary = {
        "sandbox": str(cfg.base_dir),
        "runs": runs,
        "log_events": len(records),
        "by_workflow": {k: sum(1 for r in records if r["workflow"] == k) for k in REGISTRY},
        "proposals": [r for r in records if r["kind"] == "proposal"],
        "external_actions_performed": list(ctx.gate.performed),
        "external_actions_suppressed": len(ctx.gate.suppressed),
        "notifications_delivered": len(ctx.notifier.sent),
        "real_data_files_written": [str(p) for p in real_writes],
        "all_dry_run": all(r["mode"] == "dry_run" for r in records),
        "dashboard": report,
    }
    return summary

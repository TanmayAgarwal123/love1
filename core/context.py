"""Runtime context handed to every workflow, and the per-run helper that
enforces dry-run: shadow stores, logged-not-performed external actions, and
the approval queue for anything that spends money."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from adapters.base import CalendarSource, MessageSource, Notifier, NullMessageSource
from adapters.ics import ICSCalendarSource
from adapters.notify import LocalNotifier
from adapters.whatsapp import WhatsAppExportSource

from .approvals import AWAITING, ApprovalQueue
from .config import Config
from .log import EventLog
from .store import JsonStore


class ExternalGate:
    """Every side effect that leaves this repo goes through here. In dry-run it
    is recorded as suppressed and never executed."""

    def __init__(self):
        self.performed: list[str] = []
        self.suppressed: list[str] = []

    def perform(self, kind: str, fn, live: bool):
        if not live:
            self.suppressed.append(kind)
            return None
        self.performed.append(kind)
        return fn()


@dataclass
class Context:
    cfg: Config
    now: datetime
    message_source: MessageSource
    calendar_source: CalendarSource
    notifier: Notifier
    log: EventLog
    gate: ExternalGate = field(default_factory=ExternalGate)

    def messages(self):
        return [m for m in self.message_source.messages() if m.ts <= self.now]

    def drafts(self):
        return self.message_source.drafts()

    def events(self, start, end, whose=None):
        return self.calendar_source.events(start, end, whose)

    @property
    def today(self):
        return self.now.date()

    def run(self, name: str) -> "WorkflowRun":
        return WorkflowRun(self, name)

    def approvals(self, dry: bool = False) -> ApprovalQueue:
        data = self.cfg.path("data")
        return ApprovalQueue(JsonStore(data / "approvals.json",
                                       data / ".dryrun" / "approvals.json" if dry else None, {"items": []}))


def build_context(cfg: Config, now: datetime | None = None, notifier: Notifier | None = None,
                  message_source: MessageSource | None = None,
                  calendar_source: CalendarSource | None = None) -> Context:
    tz = cfg.tz
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    if message_source is None:
        message_source = (WhatsAppExportSource(cfg) if cfg.get("messaging.channel") == "whatsapp"
                          else NullMessageSource())
    return Context(
        cfg=cfg, now=now, message_source=message_source,
        calendar_source=calendar_source or ICSCalendarSource(cfg),
        notifier=notifier or LocalNotifier(cfg.path("logs") / "nudges.log",
                                           desktop=bool(cfg.get("notifications.desktop", False))),
        log=EventLog(cfg.path("logs") / "relops.jsonl"),
    )


class WorkflowRun:
    def __init__(self, ctx: Context, name: str):
        self.ctx = ctx
        self.name = name
        self.live = ctx.cfg.is_live(name)
        self.mode = "live" if self.live else "dry_run"
        self.events: list[dict] = []

    @property
    def data_dir(self) -> Path:
        return self.ctx.cfg.path("data")

    def store(self, key: str, default) -> JsonStore:
        shadow = None if self.live else self.data_dir / ".dryrun" / f"{key}.json"
        return JsonStore(self.data_dir / f"{key}.json", shadow, default)

    def write_file(self, rel: str, text: str) -> Path:
        base = self.data_dir if self.live else self.data_dir / ".dryrun"
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def log(self, kind: str, *, trigger: str, action: str, status: str, **data) -> dict:
        rec = self.ctx.log.write(ts=self.ctx.now, workflow=self.name, mode=self.mode, kind=kind,
                                 trigger=trigger, action=action, status=status, data=data)
        self.events.append(rec)
        return rec

    def propose(self, kind: str, *, trigger: str, summary: str, payload: dict, **data) -> dict:
        """Queue a cart/order/booking. It stops here, at AWAITING_APPROVAL."""
        item = self.ctx.approvals(dry=not self.live).add(
            workflow=self.name, kind=kind, summary=summary, payload=payload, now=self.ctx.now)
        self.log("proposal", trigger=trigger, action=f"prepared {kind}: {summary} — halted for your approval "
                 f"(python cli.py approvals show {item['id']})", status=AWAITING,
                 approval_id=item["id"], proposal_kind=kind, **data)
        return item

    def notify_me(self, title: str, body: str, *, trigger: str, kind: str = "nudge", **data) -> dict:
        """Nudge YOU (never her). Dry-run logs what would be shown."""
        self.ctx.gate.perform("notify_me", lambda: self.ctx.notifier.notify(title, body), self.live)
        return self.log(kind, trigger=trigger, action=f"nudge you: {title} — {body}",
                        status="sent_to_you" if self.live else "would_nudge_you", **data)

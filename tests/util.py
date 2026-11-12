import tempfile
from datetime import datetime
from pathlib import Path

from adapters.notify import RecordingNotifier
from core.context import build_context
from core.simulate import make_sandbox


def sandbox(overrides=None):
    tmp = Path(tempfile.mkdtemp(prefix="relops-test-"))
    return make_sandbox(tmp, overrides)


def ctx_at(cfg, iso):
    now = datetime.fromisoformat(iso).replace(tzinfo=cfg.tz)
    return build_context(cfg, now=now, notifier=RecordingNotifier())


def kinds(events):
    return [e["kind"] for e in events]

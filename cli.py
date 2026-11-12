#!/usr/bin/env python3
"""Relationship Ops command line.

  python cli.py status                      # toggles + live/dry-run per workflow
  python cli.py run <workflow|all> [--now ISO] [--force]
  python cli.py due [--now ISO]             # run whatever the schedule says is due now
  python cli.py dashboard [--week-ending YYYY-MM-DD]
  python cli.py simulate-week [--start YYYY-MM-DD]
  python cli.py approvals list|show|approve|reject|done [ID] [--dry-run]
  python cli.py referee THREAD.txt [--since ISO] [--until ISO] [--last N]
  python cli.py check-draft "text"
  python cli.py crontab
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from core.approvals import APPROVED, AWAITING, DONE, REJECTED
from core.config import ROOT, Config
from core.context import build_context
from core.log import format_line
from core.schedule import crontab, due
from core.timeutil import parse_now


def _ctx(args):
    cfg = Config.load(getattr(args, "config", None))
    return build_context(cfg, now=parse_now(getattr(args, "now", None), cfg.tz))


def cmd_status(args):
    from workflows import INVOKE_ONLY, ORDER
    ctx = _ctx(args)
    cfg = ctx.cfg
    print(f"config: {cfg.source}\nmaster dry_run: {cfg.master_dry_run}\n")
    for name in ORDER:
        mode = "LIVE" if cfg.is_live(name) else "dry-run"
        sched = "invoke-only" if name in INVOKE_ONLY else "scheduled"
        print(f"  {name:15} enabled={str(cfg.enabled(name)):5}  mode={mode:8} {sched}")
    todos = cfg.todos("partner.birthday", "workflows.long_shift.order", "workflows.long_shift.service",
                      "workflows.long_shift.address_label", "workflows.random_flowers.budget_cap",
                      "workflows.random_flowers.florist")
    if todos:
        print("\nStill TODO in config:", ", ".join(todos))


def _run_one(ctx, name, **kw):
    from workflows import INVOKE_ONLY, REGISTRY
    if name in INVOKE_ONLY:
        print(f"{name} is invoke-only; use `python cli.py {name} ...`")
        return
    if not ctx.cfg.enabled(name):
        print(f"{name}: disabled in config — skipped")
        return
    events = REGISTRY[name].run(ctx, **kw)
    if not events:
        print(f"{name}: ran, nothing to do")
    for e in events:
        print(format_line(e))


def cmd_run(args):
    from workflows import INVOKE_ONLY, ORDER
    ctx = _ctx(args)
    names = [n for n in ORDER if n not in INVOKE_ONLY] if args.workflow == "all" else [args.workflow]
    for n in names:
        _run_one(ctx, n, force=args.force)


def cmd_due(args):
    ctx = _ctx(args)
    for name in due(ctx.now.replace(second=0, microsecond=0)):
        if name == "dashboard":
            cmd_dashboard(args)
        else:
            _run_one(ctx, name)


def cmd_dashboard(args):
    from dashboard import sunday
    ctx = _ctx(args)
    we = date.fromisoformat(args.week_ending) if getattr(args, "week_ending", None) else None
    out, md = sunday.run(ctx, week_ending=we)
    print(md)
    print(f"(saved to {out})")


def cmd_simulate(args):
    from core.simulate import simulate_week
    s = simulate_week(date.fromisoformat(args.start))
    print(f"Simulated week from {args.start} in sandbox {s['sandbox']}")
    print(f"Runs: {json.dumps(s['runs'])}")
    print(f"Log events: {s['log_events']}  by workflow: {json.dumps(s['by_workflow'])}")
    print(f"Proposals (all halted at {AWAITING}):")
    for p in s["proposals"]:
        print("  - " + format_line(p))
    print(f"External actions performed: {len(s['external_actions_performed'])}  "
          f"(suppressed in dry-run: {s['external_actions_suppressed']})")
    print(f"Notifications delivered: {s['notifications_delivered']}")
    print(f"Real data files written: {len(s['real_data_files_written'])}")
    if s["dashboard"]:
        print("\n" + s["dashboard"][1])
    ok = (not s["external_actions_performed"] and not s["real_data_files_written"]
          and s["notifications_delivered"] == 0 and s["all_dry_run"])
    print("RESULT:", "PASS — zero external actions" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def cmd_approvals(args):
    ctx = _ctx(args)
    q = ctx.approvals(dry=args.dry_run)
    if args.action == "list":
        items = q.list()
        if not items:
            print("No proposals." + ("" if args.dry_run else " (dry-run proposals: add --dry-run)"))
        for i in items:
            print(f"{i['id']:12} {i['status']:18} {i['workflow']:15} {i['summary']}")
        return
    if not args.id:
        sys.exit("give an approval id")
    item = q.get(args.id)
    if item is None:
        sys.exit(f"no approval {args.id}")
    if args.action == "show":
        print(json.dumps(item, indent=2, ensure_ascii=False))
        return
    new = {"approve": APPROVED, "reject": REJECTED, "done": DONE}[args.action]
    item = q.transition(args.id, new, ctx.now)
    kind = {APPROVED: "approved", REJECTED: "rejected", DONE: "done"}[new]
    items_n = len(item["payload"].get("lines", [])) or 1
    ctx.log.write(ts=ctx.now, workflow=item["workflow"], mode="dry_run" if args.dry_run else "live", kind=kind,
                  trigger=f"you ran approvals {args.action} {args.id}", action=f"{item['summary']} -> {new}",
                  status=new, data={"approval_id": item["id"], "items": items_n})
    if new == APPROVED:
        p = item["payload"]
        print("Approved. Nothing has been bought, booked or sent — finish it yourself here:")
        for link in filter(None, [p.get("cart_url"), p.get("link")] + [l.get("url") for l in p.get("lines", [])]):
            print("  ", link)
    elif new == DONE and item["workflow"] == "date_night":
        from workflows import date_night
        date_night.on_done(ctx, item, live=not args.dry_run)
        print("Marked held; restaurant marked visited.")
    else:
        print(f"{args.id} -> {new}")


def cmd_referee(args):
    from workflows import referee
    ctx = _ctx(args)
    if not ctx.cfg.enabled("referee"):
        sys.exit("referee disabled in config")
    _, out, md = referee.run(ctx, thread=args.thread, since=args.since, until=args.until, last=args.last)
    print(md)
    print(f"(private draft saved to {out} — deliver the apology in person)")


def cmd_check_draft(args):
    from workflows.reply_monitor import check_text
    cfg = Config.load(args.config)
    if check_text(cfg, args.text):
        print(f'URGENT: "{args.text}" is a one-word reply. Write her a real sentence.')
        sys.exit(2)
    print("OK")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Relationship Ops")
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("run"); p.add_argument("workflow"); p.add_argument("--now"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("due"); p.add_argument("--now"); p.set_defaults(fn=cmd_due)
    p = sub.add_parser("dashboard"); p.add_argument("--week-ending"); p.add_argument("--now"); p.set_defaults(fn=cmd_dashboard)
    p = sub.add_parser("simulate-week"); p.add_argument("--start", default="2026-11-16"); p.set_defaults(fn=cmd_simulate)
    p = sub.add_parser("approvals"); p.add_argument("action", choices=["list", "show", "approve", "reject", "done"])
    p.add_argument("id", nargs="?"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--now"); p.set_defaults(fn=cmd_approvals)
    p = sub.add_parser("referee"); p.add_argument("thread"); p.add_argument("--since"); p.add_argument("--until")
    p.add_argument("--last", type=int); p.add_argument("--now"); p.set_defaults(fn=cmd_referee)
    p = sub.add_parser("check-draft"); p.add_argument("text"); p.set_defaults(fn=cmd_check_draft)
    sub.add_parser("crontab").set_defaults(fn=lambda a: print(crontab(str(ROOT)), end=""))
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

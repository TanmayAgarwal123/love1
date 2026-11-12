"""Sample-data trigger test per workflow: each must emit the log line proving it fired."""
import json
import unittest
from pathlib import Path

from core.approvals import AWAITING
from core.config import ROOT
from tests.util import ctx_at, kinds, sandbox
from workflows import date_night, friends_crm, gift_list, long_shift, random_flowers, referee, reply_monitor


class ReplyMonitor(unittest.TestCase):
    def test_nudges_after_20_min_and_flags_k(self):
        cfg = sandbox()
        ev = reply_monitor.run(ctx_at(cfg, "2026-11-22T14:20"))
        self.assertIn("nudge", kinds(ev))
        nudge = next(e for e in ev if e["kind"] == "nudge")
        self.assertEqual(nudge["status"], "would_nudge_you")
        self.assertIn("one_word_reply", kinds(ev))
        self.assertIn("one_word_draft", kinds(ev))
        k = next(e for e in ev if e["kind"] == "one_word_reply")
        self.assertEqual((k["status"], k["data"]["text"]), ("URGENT", "k"))
        gaps = [e["data"]["minutes"] for e in ev if e["kind"] == "reply_gap"]
        self.assertIn(35.0, gaps)

    def test_no_nudge_before_threshold(self):
        cfg = sandbox()
        ev = reply_monitor.run(ctx_at(cfg, "2026-11-22T14:15"))
        self.assertNotIn("nudge", kinds(ev))

    def test_idempotent(self):
        cfg = sandbox()
        reply_monitor.run(ctx_at(cfg, "2026-11-22T14:25"))
        self.assertEqual(reply_monitor.run(ctx_at(cfg, "2026-11-22T14:30")), [])


class GiftList(unittest.TestCase):
    def test_saves_mentions_with_context(self):
        cfg = sandbox()
        ev = gift_list.run(ctx_at(cfg, "2026-11-19T00:00"))
        saved = [e["data"]["item"] for e in ev if e["kind"] == "gift_saved"]
        self.assertEqual(saved, ["ceramic cat planter", "silk scrunchie set"])
        db = json.loads((cfg.path("data") / ".dryrun" / "gifts.json").read_text())
        self.assertEqual(db["items"][0]["contexts"][0]["date"], "2026-11-10")

    def test_cart_14_days_before_birthday_halts(self):
        cfg = sandbox()
        self.assertNotIn("proposal", kinds(gift_list.run(ctx_at(cfg, "2026-11-21T12:00"))))
        ev = gift_list.run(ctx_at(cfg, "2026-11-22T09:00"))
        prop = next(e for e in ev if e["kind"] == "proposal")
        self.assertEqual(prop["status"], AWAITING)
        ap = ctx_at(cfg, "2026-11-22T09:00").approvals(dry=True).list()[0]
        self.assertEqual(ap["status"], AWAITING)
        self.assertEqual(ap["payload"]["state"], AWAITING)
        self.assertTrue(all("amazon.com" in l["url"] for l in ap["payload"]["lines"]))
        self.assertEqual(gift_list.run(ctx_at(cfg, "2026-11-23T09:00")), [])  # once per year


class DateNight(unittest.TestCase):
    def test_monday_finds_free_evening_and_top_place(self):
        cfg = sandbox()
        ev = date_night.run(ctx_at(cfg, "2026-11-16T09:00"))
        prop = next(e for e in ev if e["kind"] == "proposal")
        self.assertEqual(prop["data"]["date"], "2026-11-20")       # Friday: only shared free evening preferred
        self.assertEqual(prop["data"]["place"], "Saffron Lane")    # her mention beats seed list
        self.assertEqual(prop["status"], AWAITING)

    def test_not_monday_does_nothing_unless_forced(self):
        cfg = sandbox()
        self.assertNotIn("proposal", kinds(date_night.run(ctx_at(cfg, "2026-11-17T09:00"))))
        self.assertIn("proposal", kinds(date_night.run(ctx_at(cfg, "2026-11-17T09:00"), force=True)))


class FriendsCRM(unittest.TestCase):
    def test_logs_friends_and_briefs_before_event(self):
        cfg = sandbox()
        ev = friends_crm.run(ctx_at(cfg, "2026-11-20T09:00"))
        names = {e["data"]["friend"] for e in ev if e["kind"] == "friend_logged"}
        self.assertTrue({"Anjali", "Meera", "Priya", "Rahul"} <= names)
        self.assertFalse(names & {"Clinic", "Saturday", "Partner", "Saffron", "Lumos"})
        b = next(e for e in ev if e["kind"] == "briefing")
        self.assertEqual(set(b["data"]["friends"]), {"Priya", "Rahul"})
        md = next((cfg.path("data") / ".dryrun" / "briefings").glob("*.md")).read_text()
        self.assertIn("coming for dinner Saturday", md)


class LongShift(unittest.TestCase):
    def test_12h_shift_prepares_6pm_order(self):
        cfg = sandbox()
        ev = long_shift.run(ctx_at(cfg, "2026-11-18T13:00"))
        prop = next(e for e in ev if e["kind"] == "proposal")
        self.assertEqual(prop["status"], AWAITING)
        ap = ctx_at(cfg, "2026-11-18T13:00").approvals(dry=True).list()[0]
        self.assertTrue(ap["payload"]["deliver_at"].startswith("2026-11-19T18:00"))

    def test_short_shift_ignored(self):
        cfg = sandbox()
        self.assertEqual(long_shift.run(ctx_at(cfg, "2026-11-16T06:00")), [])  # 9h clinic


class RandomFlowers(unittest.TestCase):
    def test_window_is_6_to_8_weeks_and_order_halts(self):
        cfg = sandbox()
        ev = random_flowers.run(ctx_at(cfg, "2026-11-16T10:00"))
        plan = next(e for e in ev if e["kind"] == "plan")["data"]
        from datetime import date
        length = (date.fromisoformat(plan["window_end"]) - date.fromisoformat(plan["window_start"])).days + 1
        self.assertTrue(42 <= length <= 56)
        target = date.fromisoformat(plan["date"])
        order_day = target.fromordinal(target.toordinal() - 2)
        ev = random_flowers.run(ctx_at(cfg, f"{order_day}T10:00"))
        prop = next(e for e in ev if e["kind"] == "proposal")
        self.assertEqual(prop["status"], AWAITING)
        ap = ctx_at(cfg, f"{order_day}T10:00").approvals(dry=True).list()[0]
        self.assertEqual(ap["payload"]["deliver_on"], plan["date"])
        self.assertEqual(ap["payload"]["budget_cap"], 75)

    def test_avoids_birthday(self):
        from datetime import date, timedelta
        cfg = sandbox()
        for k in range(60):
            p = random_flowers.new_plan(cfg, date(2026, 11, 1) + timedelta(days=k))
            self.assertGreater(abs((date.fromisoformat(p["date"]) - date(2026, 12, 6)).days), 4)


class Referee(unittest.TestCase):
    def test_summarizes_reads_and_drafts_in_person_apology(self):
        cfg = sandbox()
        events, out, md = referee.run(ctx_at(cfg, "2026-11-22T10:00"), thread=str(ROOT / "samples" / "heated_thread.txt"))
        self.assertEqual(events[0]["kind"], "referee_draft")
        for expected in ("overreacting", "always", "one-word", "went quiet", "'but'", "IN PERSON",
                         "Do not paste this into the chat", "I'm sorry I"):
            self.assertIn(expected, md)
        self.assertTrue(Path(out).exists())

    def test_requires_explicit_thread(self):
        cfg = sandbox()
        with self.assertRaises(SystemExit):
            referee.run(ctx_at(cfg, "2026-11-22T10:00"))


class Toggles(unittest.TestCase):
    def test_disabled_workflow_is_skipped_by_cli(self):
        import io, contextlib, cli
        cfg = sandbox({"workflows": {"gift_list": {"enabled": False}}})
        import yaml
        p = cfg.base_dir / "cfg.yaml"
        raw = dict(cfg.raw); p.write_text(yaml.safe_dump(raw))
        buf = io.StringIO()
        import os
        os.environ["RELOPS_CONFIG"] = str(p)
        try:
            from core.config import Config
            c = Config.load(p, base_dir=cfg.base_dir)
            self.assertFalse(c.enabled("gift_list"))
            self.assertTrue(c.enabled("date_night"))
        finally:
            del os.environ["RELOPS_CONFIG"]

    def test_live_requires_master_switch_and_own_flag(self):
        cfg = sandbox({"workflows": {"reply_monitor": {"live": True}}})
        cfg.raw["workflows"]["reply_monitor"]["live"] = True
        self.assertFalse(cfg.is_live("reply_monitor"))           # master dry_run still on
        cfg.raw["dry_run"] = False
        self.assertTrue(cfg.is_live("reply_monitor"))
        self.assertFalse(cfg.is_live("gift_list"))               # others stay dry
        ctx = ctx_at(cfg, "2026-11-22T14:20")
        ev = reply_monitor.run(ctx)
        self.assertEqual(next(e for e in ev if e["kind"] == "nudge")["status"], "sent_to_you")
        self.assertEqual(len(ctx.notifier.sent), 1)               # the nudge went to YOU (local notifier)
        self.assertTrue((cfg.path("data") / "reply_monitor_state.json").exists())


if __name__ == "__main__":
    unittest.main()

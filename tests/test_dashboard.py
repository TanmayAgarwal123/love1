import unittest
from datetime import date

from core.config import Config, ROOT
from dashboard.sunday import render, week_metrics


def rec(ts, wf, kind, **data):
    return {"ts": ts, "workflow": wf, "mode": "live", "kind": kind, "trigger": "", "action": "", "status": "", "data": data}


SAMPLE = [
    # last week (Nov 9–15): fast replies, a date night booked + held, 2 gifts saved, 1 cart approved
    rec("2026-11-09T10:00:00-05:00", "reply_monitor", "reply_gap", minutes=4, late=False),
    rec("2026-11-10T10:00:00-05:00", "reply_monitor", "reply_gap", minutes=6, late=False),
    rec("2026-11-10T11:00:00-05:00", "date_night", "approved", items=1),
    rec("2026-11-13T23:00:00-05:00", "date_night", "done", items=1),
    rec("2026-11-11T10:00:00-05:00", "gift_list", "gift_saved", item="a"),
    rec("2026-11-12T10:00:00-05:00", "gift_list", "gift_saved", item="b"),
    rec("2026-11-12T11:00:00-05:00", "gift_list", "approved", items=2),
    # this week (Nov 16–22): slower, two k's, nothing booked
    rec("2026-11-17T12:45:00-05:00", "reply_monitor", "reply_gap", minutes=35, late=True),
    rec("2026-11-19T07:08:00-05:00", "reply_monitor", "reply_gap", minutes=28, late=True),
    rec("2026-11-20T10:00:00-05:00", "reply_monitor", "reply_gap", minutes=15, late=False),
    rec("2026-11-17T12:45:00-05:00", "reply_monitor", "one_word_reply", text="k"),
    rec("2026-11-18T09:00:00-05:00", "reply_monitor", "one_word_reply", text="fine"),
    rec("2026-11-18T10:00:00-05:00", "gift_list", "gift_saved", item="c"),
]


class Dashboard(unittest.TestCase):
    def test_four_metrics_with_week_over_week(self):
        cfg = Config.load(ROOT / "config.example.yaml")
        md = render(cfg, SAMPLE, date(2026, 11, 22))
        for label in ("Average reply time", "Date nights booked / held", "Gifts saved / ordered",
                      "'k'-style replies sent (target 0)", "This week", "Last week"):
            self.assertIn(label, md)
        self.assertIn("| Average reply time | 26.0 min | 5.0 min | ▼ worse |", md)
        self.assertIn("Reply time slipped to 26 min (from 5) — 2 thread(s) went past 20 min on Tue/Thu", md)
        self.assertIn("'k'-style replies up to 2 (from 0, target 0)", md)
        self.assertIn("Date nights booked dropped to 0 (from 1)", md)
        self.assertIn("Date nights held dropped to 0 (from 1)", md)
        self.assertIn("Gifts saved dropped to 1 (from 2)", md)
        self.assertIn("Gifts ordered dropped to 0 (from 2)", md)
        self.assertIn("Dec 06", md)

    def test_no_drop_message(self):
        cfg = Config.load(ROOT / "config.example.yaml")
        md = render(cfg, SAMPLE[:7], date(2026, 11, 15))
        self.assertIn("Nothing dropped", md)

    def test_metrics_counts(self):
        m = week_metrics(SAMPLE, date(2026, 11, 9))
        self.assertEqual((m["date_nights_booked"], m["date_nights_held"], m["gifts_saved"], m["gifts_ordered"]), (1, 1, 2, 2))


if __name__ == "__main__":
    unittest.main()

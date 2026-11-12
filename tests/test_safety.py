"""The non-negotiables, verified by searching the code — not by intention."""
import inspect
import re
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from core.config import ROOT, Config

CODE = [p for p in ROOT.rglob("*.py") if "tests" not in p.parts and ".git" not in p.parts]

# Anything that could send a message to someone, or complete a purchase.
FORBIDDEN = [
    r"send_message", r"sendMessage", r"send_text", r"smtplib", r"sendmail", r"twilio", r"pywhatkit",
    r"whatsapp\.send", r"wa\.me/", r"api\.whatsapp", r"graph\.facebook", r"imessage", r"osascript.*Messages",
    r"\bcheckout\b", r"place_order", r"submit_order", r"buy_now", r"\bpurchase\(", r"\bpay\(", r"stripe",
    r"paypal", r"card_number", r"\bcvv\b", r"selenium", r"playwright", r"pyautogui",
    r"\.post\(", r"method=['\"](POST|PUT|PATCH|DELETE)", r"requests\.", r"httpx", r"urlopen\([^)]*data=",
]


class NoSendNoBuy(unittest.TestCase):
    def test_codebase_has_no_send_or_purchase_paths(self):
        hits = []
        for p in CODE:
            text = p.read_text()
            for pat in FORBIDDEN:
                for m in re.finditer(pat, text, re.I):
                    if pat == r"osascript.*Messages":
                        continue
                    line = text[: m.start()].count("\n") + 1
                    hits.append(f"{p.relative_to(ROOT)}:{line}: {pat}")
        self.assertEqual(hits, [], "forbidden send/purchase pattern found:\n" + "\n".join(hits))

    def test_only_network_call_is_a_read_only_calendar_get(self):
        uses = [(p.relative_to(ROOT), l) for p in CODE for l in p.read_text().splitlines() if "urlopen(" in l]
        self.assertEqual(len(uses), 1)
        self.assertEqual(str(uses[0][0]), "adapters/ics.py")
        self.assertNotIn("data=", uses[0][1])

    def test_notifier_has_no_recipient(self):
        from adapters.base import Notifier
        from adapters.notify import LocalNotifier
        for cls in (Notifier, LocalNotifier):
            self.assertEqual(list(inspect.signature(cls.notify).parameters), ["self", "title", "body"])

    def test_message_source_is_read_only(self):
        from adapters.base import MessageSource
        public = {n for n in dir(MessageSource) if not n.startswith("_")}
        self.assertEqual(public, {"messages", "drafts"})

    def test_subprocess_only_for_local_desktop_popups(self):
        for p in CODE:
            for l in p.read_text().splitlines():
                if "subprocess.run(" in l:
                    self.assertEqual(str(p.relative_to(ROOT)), "adapters/notify.py")
                    self.assertTrue("notify-send" in l or "osascript" in l)

    def test_approvals_cannot_skip_your_decision(self):
        from core.approvals import AWAITING, DONE, TRANSITIONS
        self.assertNotIn(DONE, TRANSITIONS[AWAITING])
        from adapters import commerce
        names = [n for n, _ in inspect.getmembers(commerce, inspect.isfunction) if n.startswith(("build_", "prepare_"))]
        self.assertEqual(sorted(names), ["build_amazon_cart", "prepare_booking", "prepare_flower_order", "prepare_food_order"])
        tz = ZoneInfo("UTC")
        now = datetime(2026, 1, 1, tzinfo=tz)
        for payload in (commerce.build_amazon_cart([{"item": "x"}]),
                        commerce.prepare_food_order("x", "doordash", "home", now),
                        commerce.prepare_flower_order(florist="ftd", deliver_on=now.date(), budget_cap=1,
                                                      currency="USD", avoid=[], likes=[]),
                        commerce.prepare_booking(place={"name": "x"}, when=now, party=2, site="opentable")):
            self.assertEqual(payload["state"], AWAITING)


class Defaults(unittest.TestCase):
    def test_example_config_is_dry_run_everywhere(self):
        cfg = Config.load(ROOT / "config.example.yaml")
        self.assertTrue(cfg.master_dry_run)
        for name, wf in cfg.raw["workflows"].items():
            self.assertFalse(wf.get("live", False), name)
            self.assertFalse(cfg.is_live(name), name)

    def test_missing_dry_run_key_means_dry_run(self):
        self.assertTrue(Config({"workflows": {"x": {"live": True}}}).master_dry_run)
        self.assertFalse(Config({"workflows": {"x": {"live": True}}}).is_live("x"))

    def test_referee_is_never_scheduled(self):
        from core.schedule import SCHEDULE, crontab
        self.assertNotIn("referee", SCHEDULE)
        cron_lines = [l for l in (ROOT / "scheduler" / "crontab.txt").read_text().splitlines() if not l.startswith("#")]
        self.assertFalse(any("referee" in l for l in cron_lines))
        self.assertFalse(any("referee" in l for l in crontab("/x").splitlines() if not l.startswith("#")))

    def test_every_timed_workflow_has_a_schedule_entry(self):
        from core.schedule import SCHEDULE
        from workflows import INVOKE_ONLY, ORDER
        self.assertEqual({n for n in ORDER if n not in INVOKE_ONLY} | {"dashboard"}, set(SCHEDULE))

    def test_real_config_not_tracked(self):
        self.assertIn("config.yaml", (ROOT / ".gitignore").read_text().splitlines())


class SimulatedWeek(unittest.TestCase):
    def test_full_week_dry_run_zero_external_actions(self):
        from core.simulate import simulate_week
        s = simulate_week()
        self.assertEqual(s["external_actions_performed"], [])
        self.assertEqual(s["notifications_delivered"], 0)
        self.assertEqual(s["real_data_files_written"], [])
        self.assertTrue(s["all_dry_run"])
        self.assertGreater(s["external_actions_suppressed"], 0)
        kinds = {p["data"]["proposal_kind"] for p in s["proposals"]}
        self.assertEqual(kinds, {"restaurant_booking", "food_order", "amazon_cart"})
        self.assertTrue(all(p["status"] == "AWAITING_APPROVAL" for p in s["proposals"]))
        for wf in ("reply_monitor", "gift_list", "date_night", "friends_crm", "long_shift", "random_flowers"):
            self.assertGreater(s["by_workflow"][wf], 0, wf)


class Readme(unittest.TestCase):
    def test_readme_documents_each_workflow(self):
        text = (ROOT / "README.md").read_text()
        from workflows import ORDER
        for name in ORDER:
            sec = text.split(f"`{name}`", 1)
            self.assertEqual(len(sec), 2, name)
            chunk = sec[1][:900]
            for field in ("Trigger", "Data", "Approval gate"):
                self.assertIn(field, chunk, f"{name} missing {field}")


if __name__ == "__main__":
    unittest.main()

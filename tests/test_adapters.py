import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from adapters.ics import parse_ics
from adapters.whatsapp import parse_export
from core import extract

NY = ZoneInfo("America/New_York")


class WhatsApp(unittest.TestCase):
    def test_android_and_ios_formats(self):
        android = ("16/11/2026, 9:05 pm - Partner: hi\nsecond line\n"
                   "16/11/2026, 9:06 pm - Messages are end-to-end encrypted.\n"
                   "16/11/2026, 9:07 pm - Me: k")
        ms = parse_export(android, my_name="Me", partner_name="Partner", date_order="dmy", tz=NY)
        self.assertEqual([m.sender for m in ms], ["partner", "me"])
        self.assertEqual(ms[0].text, "hi\nsecond line")
        self.assertEqual(ms[0].ts.hour, 21)
        ios = "[11/16/26, 9:41:03 AM] Partner: morning"
        m = parse_export(ios, my_name="Me", partner_name="Partner", date_order="mdy", tz=NY)[0]
        self.assertEqual((m.ts.month, m.ts.day, m.ts.hour, m.sender), (11, 16, 9, "partner"))


class ICS(unittest.TestCase):
    def test_rrule_tz_and_transparent(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART;TZID=America/New_York:20261117T190000\n"
                "DTEND;TZID=America/New_York:20261117T210000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE;COUNT=3\n"
                "EXDATE;TZID=America/New_York:20261118T190000\nSUMMARY:Class\nEND:VEVENT\n"
                "BEGIN:VEVENT\nUID:b\nDTSTART:20261120T000000Z\nDTEND:20261120T010000Z\nTRANSP:TRANSPARENT\n"
                "SUMMARY:Free\nEND:VEVENT\nEND:VCALENDAR\n")
        s = datetime(2026, 11, 16, tzinfo=NY)
        evs = parse_ics(text, tz=NY, whose="mine", calendar="c", work=False, win_start=s, win_end=s + timedelta(days=14))
        classes = [e.start.day for e in evs if e.summary == "Class"]
        self.assertEqual(classes, [17, 24])  # 18th excluded by EXDATE, COUNT=3 includes it
        free = next(e for e in evs if e.summary == "Free")
        self.assertTrue(free.transparent)
        self.assertEqual(free.start.hour, 19)  # 00:00Z -> 19:00 NY


class Extract(unittest.TestCase):
    def test_wants(self):
        self.assertEqual(extract.wants("I really want a ceramic cat planter for the window"), ["ceramic cat planter"])
        self.assertEqual(extract.wants("I'd love a silk scrunchie set, mine keep snapping"), ["silk scrunchie set"])
        self.assertEqual(extract.wants("I want to sleep for a week"), [])
        self.assertEqual(extract.wants("I need a nap", ["nap"]), [])

    def test_restaurants(self):
        self.assertEqual(extract.restaurants("We should try Saffron Lane sometime"), ["Saffron Lane"])
        self.assertEqual(extract.restaurants("I want to try Lumos Kitchen too"), ["Lumos Kitchen"])

    def test_friends(self):
        self.assertEqual(set(extract.friends("Priya said she's coming Saturday with Rahul")), {"Priya", "Rahul"})
        self.assertEqual(extract.friends("Clinic till 5 on Monday"), [])


if __name__ == "__main__":
    unittest.main()

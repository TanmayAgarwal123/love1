"""Rule-based mention extraction from her messages: wants, restaurants, friends.

Deliberately conservative: a missed mention is cheaper than junk in your lists.
"""
from __future__ import annotations

import re

_APOS = str.maketrans({"’": "'", "‘": "'"})

_WANT_RES = [
    re.compile(r"\bi\s+(?:really\s+|so\s+|kinda\s+|kind of\s+|just\s+)?(?:want|need)\s+"
               r"(?!to\b|you\b|u\b|it\b|that\b|this\b|them\b|him\b|her\b|me\b|us\b)(?P<item>[^.!?,;\n]+)", re.I),
    re.compile(r"\bi(?:'d|\s+would)\s+(?:really\s+|so\s+)?love\s+"
               r"(?!to\b|you\b|u\b|it\b|that\b|this\b|them\b|him\b|her\b|us\b)(?P<item>[^.!?,;\n]+)", re.I),
    re.compile(r"\bi\s+wish\s+i\s+had\s+(?P<item>[^.!?,;\n]+)", re.I),
    re.compile(r"\bi(?:'ve|\s+have)\s+been\s+wanting\s+(?!to\b)(?P<item>[^.!?,;\n]+)", re.I),
]
_LEADING = re.compile(r"^(?:(?:a|an|the|some|new|one of those|those|these|a new|another|more)\s+)+", re.I)
_TRAILING = re.compile(r"\s+(?:for\s+(?:the|my|our|me|when|it)\b.*|so\s+bad(?:ly)?.*|soon.*|lol.*|haha.*|"
                       r"rn\b.*|right now.*|too\b.*|already.*|again.*)$", re.I)

_PLACE = r"(?P<place>(?:[A-Z][\w'&-]*)(?:\s+(?:[A-Z][\w'&-]*|&|of|de|la|and))*)"
_REST_RES = [
    re.compile(r"\b(?:[Ww]ant(?:s)?\s+to|[Ww]anna|[Ss]hould|[Gg]otta|[Hh]ave\s+to|[Ll]et'?s|[Ww]e\s+could)\s+"
               r"(?:go\s+)?(?:try|go\s+to|check\s+out|eat\s+at)\s+(?:the\s+)?" + _PLACE),
    re.compile(r"\b[Hh]ave\s+you\s+been\s+to\s+(?:the\s+)?" + _PLACE),
]

_STOP = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today", "tomorrow",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "the", "this", "that", "they", "them", "she", "her", "him", "his", "you",
    "your", "mine", "our", "we", "and", "but", "god", "omg", "lol", "lmao", "haha", "okay", "yes", "yeah",
    "nope", "work", "home", "mom", "dad", "mum", "netflix", "instagram", "whatsapp", "amazon", "uber",
    "lunch", "dinner", "breakfast", "brunch", "clinic", "hospital", "office", "class", "gym", "what",
    "when", "where", "why", "how", "who", "just", "also", "maybe", "well", "sorry", "thanks", "thank",
    "love", "babe", "baby", "dear", "christmas", "diwali", "onam", "everyone", "someone", "nobody",
}
_FRIEND_RES = [
    re.compile(r"\b(?:with|and|told|tell|from|call(?:ed)?|text(?:ed)?|meet(?:ing)?|met|saw|see|seeing|"
               r"visit(?:ing|ed)?|invite[ds]?|hanging\s+out\s+with)\s+(?P<name>[A-Z][a-z]{2,})\b"),
    re.compile(r"\b(?P<name>[A-Z][a-z]{2,})(?:'s)?\s+(?:said|says|told|called|texted|invited|wants|got|"
               r"loved|loves|is\s+coming|was\s+saying|and\s+I|asked)\b"),
]


def _clean_item(raw: str) -> str:
    s = raw.strip().translate(_APOS)
    s = _TRAILING.sub("", s)
    s = _LEADING.sub("", s).strip(" -:'\"")
    words = s.split()
    return " ".join(words[:8])


def wants(text: str, ignore: list[str] | None = None) -> list[str]:
    ignore_set = {i.lower() for i in (ignore or [])}
    text = text.translate(_APOS)
    found = []
    for rx in _WANT_RES:
        for m in rx.finditer(text):
            item = _clean_item(m.group("item"))
            if len(item) < 3 or item.lower() in ignore_set:
                continue
            if any(w in ignore_set for w in item.lower().split()) and len(item.split()) <= 2:
                continue
            if item.lower() not in (f.lower() for f in found):
                found.append(item)
    return found


def restaurants(text: str) -> list[str]:
    text = text.translate(_APOS)
    out = []
    for rx in _REST_RES:
        for m in rx.finditer(text):
            words = m.group("place").split()
            while words and words[-1].lower() in {"and", "of", "de", "la", "&"}:
                words.pop()
            if not words or words[0].lower() in _STOP or len(words) > 5:
                continue
            name = " ".join(words)
            if name not in out:
                out.append(name)
    return out


def friends(text: str, known: list[str] | None = None, exclude: list[str] | None = None) -> list[str]:
    text = text.translate(_APOS)
    excl = {e.lower() for e in (exclude or [])}
    out: list[str] = []

    def add(n: str):
        if n.lower() in _STOP or n.lower() in excl:
            return
        if n not in out:
            out.append(n)

    for k in known or []:
        if re.search(rf"\b{re.escape(k)}\b", text, re.I):
            add(k)
    for rx in _FRIEND_RES:
        for m in rx.finditer(text):
            add(m.group("name"))
    return out


def mentions_name(name: str, *texts: str) -> bool:
    rx = re.compile(rf"\b{re.escape(name)}\b", re.I)
    return any(t and rx.search(t) for t in texts)

"""7. Argument referee. INVOKE-ONLY (never scheduled).

You point it at a heated thread (a WhatsApp export file). It summarizes what
each of you actually said, gives you an honest read on where YOU went wrong,
and drafts an apology for you to deliver IN PERSON. Output is a local draft
file for you. It never contacts anyone.

Analysis is local and rule-based on purpose: the thread never leaves your machine.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from adapters.whatsapp import parse_export

NAME = "referee"

CHECKS = {
    "absolutes": (["you always", "you never", "every time you", "you're always", "you are always", "you're never"],
                  "used 'always/never' about her", "said 'you always' / 'you never', which wasn't fair or true",
                  "talk about the specific thing that happened, not 'always'"),
    "blame": (["your fault", "you made me", "because of you", "you started", "overreacting", "calm down",
               "you're being", "you are being", "dramatic", "crazy", "too sensitive"],
              "put it on her / told her how to feel", "put it on you and told you how to feel instead of owning my part",
              "own my part first, before anything else"),
    "deflect": (["i didn't do anything", "that's not what i said", "i never said", "what about you", "you also",
                 "you do it too", "not my fault", "i was just"],
                "got defensive / deflected", "got defensive instead of listening to you",
                "listen all the way through before I explain myself"),
    "sarcasm": (["wow.", "sure.", "great.", "fine.", "ok then", "whatever", "lol", "cool story", "if you say so"],
                "was sarcastic or dismissive", "was sarcastic when you were being serious",
                "keep my tone straight when you're telling me something matters"),
    "non_apology": (["sorry but", "sorry if", "sorry you feel", "i'm sorry, but", "sorry, but"],
                    "apologized with a 'but' / 'if'", "apologized with a 'but' attached",
                    "apologize without conditions"),
}
_ONE_WORD = {"k", "kk", "ok", "okay", "fine", "sure", "whatever", "cool", "hmm", "mhm", "yeah", "ya"}
_HER_NEED = re.compile(r"\b(i feel|i felt|i need|i want you to|you didn't|you don't|you never|it hurts|"
                       r"hurt me|why can't you|why didn't you|i just wanted|all i wanted)\b", re.I)
_WORD = re.compile(r"[a-z']{4,}")


def _norm(t):
    return re.sub(r"[^\w]", "", t.lower())


def analyze(msgs, threshold_minutes: float = 20) -> dict:
    msgs = [m for m in msgs if m.sender in ("me", "partner")]
    findings: list[dict] = []
    for i, m in enumerate(msgs):
        if m.sender != "me":
            continue
        low = m.text.lower()
        for key, (phrases, label, *_rest) in CHECKS.items():
            hit = next((p for p in phrases if p in low), None)
            if hit:
                findings.append({"check": key, "label": label, "quote": m.text, "at": m.ts})
        if _norm(m.text) in _ONE_WORD and i > 0 and msgs[i - 1].sender == "partner":
            findings.append({"check": "one_word", "label": "gave a one-word reply", "quote": m.text, "at": m.ts})
        letters = [w for w in re.findall(r"[A-Za-z]{3,}", m.text)]
        if len(letters) >= 3 and sum(w.isupper() for w in letters) / len(letters) > 0.6:
            findings.append({"check": "shouting", "label": "shouted (ALL CAPS)", "quote": m.text, "at": m.ts})
        if i > 0 and msgs[i - 1].sender == "partner":
            gap = (m.ts - msgs[i - 1].ts).total_seconds() / 60
            if gap > threshold_minutes:
                findings.append({"check": "went_quiet", "label": f"went quiet for {gap:.0f} min mid-argument",
                                 "quote": msgs[i - 1].text, "at": msgs[i - 1].ts})
    for i, m in enumerate(msgs):
        if m.sender == "partner" and "?" in m.text:
            nxt = next((x for x in msgs[i + 1:] if x.sender == "me"), None)
            if nxt is None:
                continue
            if msgs[i + 1:] and msgs[i + 1].sender == "partner":
                continue  # she kept talking; judge her last message instead
            q, a = set(_WORD.findall(m.text.lower())), set(_WORD.findall(nxt.text.lower()))
            if len(nxt.text.split()) < 6 and not (q & a):
                findings.append({"check": "unanswered", "label": "didn't answer her question",
                                 "quote": m.text, "at": m.ts})
    her = [m for m in msgs if m.sender == "partner"]
    mine = [m for m in msgs if m.sender == "me"]
    needs = [m for m in her if _HER_NEED.search(m.text)]
    return {"her": her, "mine": mine, "needs": needs, "findings": findings,
            "start": msgs[0].ts if msgs else None, "end": msgs[-1].ts if msgs else None}


def _key_points(ms, n=4):
    return sorted(ms, key=lambda m: len(m.text), reverse=True)[:n]


_PHRASE = {k: (v[2], v[3]) for k, v in CHECKS.items()}
_PHRASE.update({
    "one_word": ("gave you one-word answers when you were trying to talk to me",
                 "answer you properly — even if it's 'give me ten minutes, then I'm all yours'"),
    "shouting": ("raised my voice at you", "slow down and lower my voice when I'm heated"),
    "went_quiet": ("went quiet and left you waiting in the middle of it",
                   "say 'I need a break, I'll be back at X' instead of disappearing"),
    "unanswered": ("didn't answer what you actually asked me", "answer your actual question first"),
})


def render(a: dict, labels=("Her", "Me")) -> str:
    her_l, me_l = labels
    L = ["# Argument referee — private draft for you", "",
         f"_Thread: {a['start']:%a %b %d %H:%M} → {a['end']:%a %b %d %H:%M} · {len(a['her'])} messages from {her_l}, "
         f"{len(a['mine'])} from you. Nothing was sent to anyone._" if a["start"] else "_Empty thread._", "",
         f"## What {her_l} actually said"]
    for m in (a["needs"] or _key_points(a["her"]))[:6]:
        L.append(f"- {m.ts:%H:%M} “{m.text}”")
    L += ["", "## What you actually said"]
    for m in _key_points(a["mine"]):
        L.append(f"- {m.ts:%H:%M} “{m.text}”")
    L += ["", "## Honest read: where you went wrong"]
    if a["findings"]:
        seen = set()
        for f in sorted(a["findings"], key=lambda f: f["at"]):
            L.append(f"- **{f['label']}** — {f['at']:%H:%M}: “{f['quote'][:140]}”")
            seen.add(f["check"])
    else:
        L.append("- The pattern checks didn't catch an obvious misstep. That doesn't clear you — reread what "
                 "she said above and ask what she needed that you didn't give.")
    if a["needs"]:
        L += ["", "## What she was asking for"]
        for m in a["needs"][:4]:
            L.append(f"- “{m.text}”")
    L += ["", "## Apology draft — deliver IN PERSON", "",
          "> Do not paste this into the chat. Say it face to face, in your own words, and then listen.", ""]
    L += [f"> {line}" if line else ">" for line in apology(a).splitlines()]
    return "\n".join(L) + "\n"


def apology(a: dict) -> str:
    checks = []
    for f in sorted(a["findings"], key=lambda f: f["at"]):
        if f["check"] not in checks:
            checks.append(f["check"])
    owns = [_PHRASE[c][0] for c in checks[:4]] or ["didn't listen to you as well as I should have"]
    fixes = [_PHRASE[c][1] for c in checks[:3]] or ["slow down and actually hear you next time"]
    need = a["needs"][0].text if a["needs"] else (a["her"][-1].text if a["her"] else "")
    lines = ["I've been thinking about our argument, and I want to say this properly.", ""]
    if need:
        q = need[:160].rstrip()
        lines.append(f"You told me “{q}”" + ("" if q[-1:] in ".!?" else ".") + " You were right to tell me that.")
    lines.append("I'm sorry I " + (owns[0] if len(owns) == 1 else ", ".join(owns[:-1]) + ", and " + owns[-1]) + ".")
    lines.append("That wasn't fair to you, and there's no 'but' here.")
    lines.append("")
    lines.append("What I'm going to do differently: I'll " + "; I'll ".join(fixes) + ".")
    lines.append("")
    lines.append("Is there anything else you need from me right now?")
    return "\n".join(lines)


def run(ctx, thread: str | None = None, since: str | None = None, until: str | None = None,
        last: int | None = None, **_):
    if not thread:
        raise SystemExit("referee is invoke-only: python cli.py referee path/to/thread.txt [--last N]")
    r = ctx.run(NAME)
    w = ctx.cfg.get("messaging.whatsapp", {}) or {}
    msgs = parse_export(Path(thread).read_text(encoding="utf-8", errors="replace"),
                        my_name=str(w.get("my_name", "Me")), partner_name=str(w.get("partner_name", "Partner")),
                        date_order=w.get("date_order", "dmy"), tz=ctx.cfg.tz, source=Path(thread).name)
    tz = ctx.cfg.tz
    if since:
        s = datetime.fromisoformat(since)
        msgs = [m for m in msgs if m.ts >= (s if s.tzinfo else s.replace(tzinfo=tz))]
    if until:
        u = datetime.fromisoformat(until)
        msgs = [m for m in msgs if m.ts <= (u if u.tzinfo else u.replace(tzinfo=tz))]
    if last:
        msgs = msgs[-int(last):]
    a = analyze(msgs, float(ctx.cfg.wf(NAME).get("threshold_minutes", 20)))
    md = render(a, (str(ctx.cfg.get("partner.label", "Her")), "Me"))
    # The referee only writes a private local draft, so it always writes to data/referee/.
    out = ctx.cfg.path("data") / "referee" / f"{ctx.now:%Y%m%d-%H%M}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    r.log("referee_draft", trigger=f"invoked on {Path(thread).name} ({len(msgs)} messages)",
          action=f"wrote private draft for you -> {out}; {len(a['findings'])} issue(s) found",
          status="draft_for_you", findings=len(a["findings"]))
    return r.events, out, md

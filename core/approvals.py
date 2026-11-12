"""Approval queue. Money-touching workflows end here.

States: AWAITING_APPROVAL -> APPROVED | REJECTED ; APPROVED -> DONE | REJECTED.
Approving only records your decision and shows you the link(s). Nothing in
this codebase pays, books or orders on your behalf: you finish it yourself.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from .store import JsonStore

AWAITING = "AWAITING_APPROVAL"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
DONE = "DONE"

TRANSITIONS = {
    AWAITING: {APPROVED, REJECTED},
    APPROVED: {DONE, REJECTED},
    REJECTED: set(),
    DONE: set(),
}


class ApprovalQueue:
    def __init__(self, store: JsonStore):
        self.store = store

    def _load(self):
        return self.store.load()

    def add(self, *, workflow: str, kind: str, summary: str, payload: dict, now: datetime) -> dict:
        db = self._load()
        raw = f"{workflow}|{kind}|{summary}|{now.isoformat()}|{len(db['items'])}"
        item = {
            "id": f"{workflow[:4]}-{hashlib.sha1(raw.encode()).hexdigest()[:6]}",
            "workflow": workflow,
            "kind": kind,
            "summary": summary,
            "payload": payload,
            "status": AWAITING,
            "created": now.isoformat(timespec="seconds"),
            "history": [{"status": AWAITING, "at": now.isoformat(timespec="seconds")}],
        }
        db["items"].append(item)
        self.store.save(db)
        return item

    def list(self, status: str | None = None) -> list[dict]:
        items = self._load()["items"]
        return [i for i in items if status is None or i["status"] == status]

    def get(self, approval_id: str) -> dict | None:
        return next((i for i in self._load()["items"] if i["id"] == approval_id), None)

    def transition(self, approval_id: str, new_status: str, now: datetime, note: str = "") -> dict:
        db = self._load()
        item = next((i for i in db["items"] if i["id"] == approval_id), None)
        if item is None:
            raise KeyError(f"No approval with id {approval_id}")
        if new_status not in TRANSITIONS[item["status"]]:
            raise ValueError(f"Cannot go from {item['status']} to {new_status}")
        item["status"] = new_status
        item["history"].append({"status": new_status, "at": now.isoformat(timespec="seconds"), "note": note})
        self.store.save(db)
        return item

"""Notion adapter interface (NOT wired).

You chose local JSON stores, so this is a placeholder showing the seam. To
move a store to Notion, implement load()/save() with the same shape as
core.store.JsonStore against the Notion API (needs an integration token and
the database IDs), then construct it in core/context.WorkflowRun.store().
"""
from __future__ import annotations


class NotionStore:
    def __init__(self, database_id: str, token_env: str = "NOTION_TOKEN", default=None):
        self.database_id = database_id
        self.token_env = token_env
        self.default = default

    def load(self):
        raise NotImplementedError("Notion access not configured — using local JSON stores (data/).")

    def save(self, data):
        raise NotImplementedError("Notion access not configured — using local JSON stores (data/).")

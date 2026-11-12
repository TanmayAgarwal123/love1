"""Local JSON data stores (gift list, restaurants, friends CRM, state).

In dry-run, reads fall through shadow -> real, and writes go ONLY to the
shadow copy under data/.dryrun/, so real data never changes.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path


class JsonStore:
    def __init__(self, real_path: Path, shadow_path: Path | None = None, default=None):
        self.real_path = Path(real_path)
        self.shadow_path = Path(shadow_path) if shadow_path else None
        self.default = default if default is not None else {}

    @property
    def write_path(self) -> Path:
        return self.shadow_path or self.real_path

    def exists(self) -> bool:
        return any(p and p.exists() for p in (self.shadow_path, self.real_path))

    def load(self):
        for p in (self.shadow_path, self.real_path):
            if p and p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(self.default, dict) and isinstance(data, dict):
                    for k, v in self.default.items():
                        data.setdefault(k, copy.deepcopy(v))
                return data
        return copy.deepcopy(self.default)

    def save(self, data) -> None:
        p = self.write_path
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, p)

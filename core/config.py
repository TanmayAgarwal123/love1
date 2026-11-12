"""One config file, read by every workflow."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent


def deep_merge(base: dict, over: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def config_path(explicit=None) -> Path:
    for p in (explicit, os.environ.get("RELOPS_CONFIG"), ROOT / "config.yaml", ROOT / "config.example.yaml"):
        if p and Path(p).exists():
            return Path(p)
    raise FileNotFoundError("No config.yaml or config.example.yaml found")


class Config:
    def __init__(self, raw: dict, path: Path | None = None, base_dir: Path | None = None):
        self.raw = raw
        self.source = path
        self.base_dir = Path(base_dir or ROOT)

    @classmethod
    def load(cls, path=None, overrides: dict | None = None, base_dir=None) -> "Config":
        p = config_path(path)
        raw = yaml.safe_load(p.read_text()) or {}
        return cls(deep_merge(raw, overrides), p, base_dir)

    def get(self, dotted: str, default=None):
        cur = self.raw
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.get("timezone", "UTC"))

    @property
    def master_dry_run(self) -> bool:
        # Missing key => dry-run. Only an explicit `dry_run: false` lifts the master switch.
        return self.get("dry_run", True) is not False

    def wf(self, name: str) -> dict:
        return self.get(f"workflows.{name}", {}) or {}

    def enabled(self, name: str) -> bool:
        return bool(self.wf(name).get("enabled", False))

    def is_live(self, name: str) -> bool:
        return (not self.master_dry_run) and self.wf(name).get("live", False) is True

    def path(self, key: str) -> Path:
        p = Path(self.get(f"paths.{key}", key))
        return p if p.is_absolute() else self.base_dir / p

    def resolve(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else self.base_dir / p

    def todos(self, *dotted_keys: str) -> list[str]:
        """Keys whose value is missing or still a TODO placeholder."""
        out = []
        for k in dotted_keys:
            v = self.get(k)
            if v is None or (isinstance(v, str) and v.strip().upper().startswith("TODO")):
                out.append(k)
        return out

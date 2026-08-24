"""Config loading: YAML file merged over defaults, with env overrides."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "niche": "science explained simply",
    "audience": "curious adults with no science background",
    "tone": "calm, factual, never sensational",
    "provider": "manual",
    "clips_per_video": 6,
    "clip_seconds": 10,
    "aspect_ratio": "9:16",
    "paths": {
        "work_dir": "./work",
        "inbox_dir": "./inbox",
        "output_dir": "./out",
    },
    "sync": {
        "enabled": False,
        "method": "copy",
        "dest": "",
        "rclone_remote": "",
        "include_clips": True,
    },
    "youtube": {
        "enabled": False,
        "privacy": "private",
        "category_id": "27",
        "made_for_kids": False,
        "disclosure": "Visuals in this video are AI-generated.",
    },
    "models": {
        "text": "gemini-2.5-flash",
        "video": "veo-3.0-generate-001",
    },
    "quota": {
        "daily_reset_hour_utc": 8,
        "min_backoff_seconds": 60,
        "max_backoff_seconds": 3600,
        "max_attempts_per_clip": 4,
    },
    "runner": {
        "target_pending_videos": 3,
        "max_videos": 0,
        "idle_seconds": 60,
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Dict-backed config with attribute access and resolved paths."""

    def __init__(self, data: dict, source: Path | None = None):
        self._data = data
        self.source = source
        root = source.parent if source else Path.cwd()
        self.work_dir = (root / data["paths"]["work_dir"]).resolve()
        self.inbox_dir = (root / data["paths"]["inbox_dir"]).resolve()
        self.output_dir = (root / data["paths"]["output_dir"]).resolve()
        self.db_path = self.work_dir / "autoshorts.db"

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    @property
    def data(self) -> dict:
        return self._data

    @property
    def api_key(self) -> str | None:
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    def ensure_dirs(self) -> None:
        for path in (self.work_dir, self.inbox_dir, self.output_dir):
            path.mkdir(parents=True, exist_ok=True)


def find_config(explicit: str | None = None) -> Path | None:
    """Locate config.yaml: explicit path, then cwd, then next to this package."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"config not found: {path}")
        return path
    for candidate in (
        Path.cwd() / "config.yaml",
        Path(__file__).resolve().parent.parent / "config.yaml",
    ):
        if candidate.exists():
            return candidate
    return None


def load(explicit: str | None = None) -> Config:
    path = find_config(explicit)
    raw: dict = {}
    if path:
        with path.open() as handle:
            raw = yaml.safe_load(handle) or {}
    merged = _deep_merge(DEFAULTS, raw)

    # Env overrides for the handful of things you'd flip per-run.
    if os.environ.get("AUTOSHORTS_PROVIDER"):
        merged["provider"] = os.environ["AUTOSHORTS_PROVIDER"]
    if os.environ.get("AUTOSHORTS_MAX_VIDEOS"):
        merged["runner"]["max_videos"] = int(os.environ["AUTOSHORTS_MAX_VIDEOS"])

    return Config(merged, path)

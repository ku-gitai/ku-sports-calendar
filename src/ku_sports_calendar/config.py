from __future__ import annotations

import json
from pathlib import Path


def load_config(path: str | Path) -> dict:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    required = ["key", "sport_name", "team_name", "season", "schedule_url", "schedule_text_url", "output_path"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"Config missing required keys: {', '.join(missing)}")
    return cfg

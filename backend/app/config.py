from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@lru_cache(maxsize=1)
def load_pricing_config() -> dict:
    with (CONFIG_DIR / "pricing.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)

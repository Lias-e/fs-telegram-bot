import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"


def load_settings():
    path = CONFIG_DIR / "settings.yaml"
    with open(path, encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    # Resolve database paths relative to project root
    db = settings.setdefault("database", {})
    for key in ("path", "backup_dir"):
        if key in db and db[key]:
            p = Path(db[key])
            if not p.is_absolute():
                db[key] = str(BASE_DIR / p)

    return settings


def load_selectors():
    path = CONFIG_DIR / "selectors.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_env(key, default=None):
    return os.environ.get(key, default)


def validate_env():
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "ADMIN_TELEGRAM_ID"]
    missing = [v for v in required if not (get_env(v) or "").strip()]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

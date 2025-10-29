# sistemas/storage.py
import json
from pathlib import Path
from django.conf import settings

USERS_FILE = Path(settings.BASE_DIR) / "users.json"

def load_users():
    if not USERS_FILE.exists():
        return []
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

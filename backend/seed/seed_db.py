"""
Creates the SQL tables and loads seed/hospitals.json (replaces existing rows).

Run from the backend folder:
    python seed/seed_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `app` is importable

from app import config  # noqa: E402
from app.db import load_seed  # noqa: E402

n = load_seed()
safe_url = config.DATABASE_URL.split("@")[-1]  # hide password when printing
print(f"Inserted {n} hospitals into {safe_url}")

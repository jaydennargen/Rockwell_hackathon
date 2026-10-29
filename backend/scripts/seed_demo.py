"""Seed demo users + orders into the configured repo (DATA_BACKEND=local or databricks).

    cd backend && python scripts/seed_demo.py           # adds anything missing
    cd backend && python scripts/seed_demo.py --reset   # local only: delete app.db first
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.repo import get_repo  # noqa: E402
from app.repo.seed import seed_demo  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    if args.reset and config.DATA_BACKEND == "local":
        config.APP_DB.unlink(missing_ok=True)
    repo = get_repo()  # LocalRepo seeds itself when empty
    seed_demo(repo)
    print(f"seeded {len(repo.list_orders())} orders into {config.DATA_BACKEND}")

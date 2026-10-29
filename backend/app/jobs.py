"""Background triage. Writes PROCESSING first (in the route), then the full report here."""
import asyncio
import logging
from datetime import datetime, timezone

from app import config
from app.repo import get_repo

log = logging.getLogger(__name__)


async def run_triage_job(order_id: str) -> None:
    repo = get_repo()
    row = repo.get_order(order_id)
    try:
        if config.PIPELINE == "mock":
            from triage.mock import mock_triage
            await asyncio.sleep(config.MOCK_DELAY_SECONDS)
            report = mock_triage(row["order"])
        else:
            from triage.pipeline import triage  # WS4
            report = await asyncio.to_thread(triage, row["order"])
        report["created_at"] = row["report"]["created_at"]
    except Exception as e:  # noqa: BLE001
        log.exception("triage failed for %s", order_id)
        report = {**row["report"], "status": "FAILED", "error": str(e),
                  "updated_at": datetime.now(timezone.utc).isoformat()}
    repo.save_report(order_id, report)

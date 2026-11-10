"""Delta tables in {UC_CATALOG}.{UC_SCHEMA} through the SQL warehouse (app/dbx.py, SDK unified auth).
Same SQL as the SQLite repo (repo/local.py: SqlRepo).

The app's service principal needs USE CATALOG, USE SCHEMA, CREATE TABLE, SELECT, and MODIFY on the schema
(see DEPLOY.md). Tables are created on first use. New submissions are also appended to
bronze_sap_repairs when that table exists (ARCHITECTURE.md §6).
"""
from __future__ import annotations

import logging

from app import config, dbx
from app.repo.local import DDL, SqlRepo

log = logging.getLogger(__name__)


class DatabricksRepo(SqlRepo):
    def __init__(self):
        self.prefix = f"{config.UC_CATALOG}.{config.APP_SCHEMA}"  # app tables; separate from gold stats
        for name, cols in DDL.items():
            self._exec(f"CREATE TABLE IF NOT EXISTS {self.t(name)} ({cols})")
        if config.AUTH_MODE == "demo":  # role picker needs the demo accounts; real orders stay untouched
            from app.repo.seed import seed_demo_users
            seed_demo_users(self)

    def t(self, name):
        return f"{self.prefix}.{name}"

    def _exec(self, sql, params=None):
        return dbx.rows(sql, params)

    def create_order(self, order, submitted_by, report):
        super().create_order(order, submitted_by, report)
        try:
            self._append_bronze(order, submitted_by)
        except Exception:  # noqa: BLE001 - the app row is written; bronze is the analytics copy
            log.exception("bronze append failed for %s", report["order_id"])

    def _append_bronze(self, order, submitted_by):
        self._exec(
            f"INSERT INTO {config.UC_CATALOG}.{config.UC_SCHEMA}.bronze_sap_repairs (`Order Number`, `Line Number`, `Catalog`, "
            "`Part Number`, `Part Description`, `Serial Number`, `Depot`, `Failure Details`, "
            "`Additional Information`, source, submitted_by, ingested_at) "
            "VALUES (:on, :ln, :cat, :pn, :pd, :sn, :dp, :fd, :ai, 'app_submission', :by, current_timestamp())",
            {"on": order["order_number"], "ln": order["line_number"], "cat": order["catalog"],
             "pn": order.get("part_number"), "pd": order.get("part_description"),
             "sn": order.get("serial_number"), "dp": order.get("depot"),
             "fd": order.get("failure_details"), "ai": order.get("additional_info"), "by": submitted_by})


"""Delta tables in {UC_CATALOG}.{UC_SCHEMA} via databricks-sql-connector (DATABRICKS_HOST,
DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN). Same SQL as the SQLite repo (repo/local.py: SqlRepo).

Not yet run against a workspace: verify table creation and the native `:param` binding on first connect.
New submissions are also appended to bronze_sap_repairs (ARCHITECTURE.md §6).
"""
from __future__ import annotations

import logging

from app import config
from app.repo.local import DDL, SqlRepo

log = logging.getLogger(__name__)


class DatabricksRepo(SqlRepo):
    def __init__(self):
        from databricks import sql as dbsql
        self._sql = dbsql
        self.conn_args = {"server_hostname": config.DATABRICKS_HOST.replace("https://", "").rstrip("/"),
                          "http_path": config.DATABRICKS_HTTP_PATH, "access_token": config.DATABRICKS_TOKEN}
        self.prefix = f"{config.UC_CATALOG}.{config.UC_SCHEMA}"
        for name, cols in DDL.items():
            self._exec(f"CREATE TABLE IF NOT EXISTS {self.t(name)} ({cols})")

    def t(self, name):
        return f"{self.prefix}.{name}"

    def _exec(self, sql, params=None):
        with self._sql.connect(**self.conn_args) as con, con.cursor() as cur:
            cur.execute(sql, params or None)
            if not cur.description:
                return []
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def create_order(self, order, submitted_by, report):
        super().create_order(order, submitted_by, report)
        try:
            self._append_bronze(order, submitted_by)
        except Exception:  # noqa: BLE001 - the app row is written; bronze is the analytics copy
            log.exception("bronze append failed for %s", report["order_id"])

    def _append_bronze(self, order, submitted_by):
        self._exec(
            f"INSERT INTO {self.t('bronze_sap_repairs')} (`Order Number`, `Line Number`, `Catalog`, "
            "`Part Number`, `Part Description`, `Serial Number`, `Depot`, `Failure Details`, "
            "`Additional Information`, source, submitted_by, ingested_at) "
            "VALUES (:on, :ln, :cat, :pn, :pd, :sn, :dp, :fd, :ai, 'app_submission', :by, current_timestamp())",
            {"on": order["order_number"], "ln": order["line_number"], "cat": order["catalog"],
             "pn": order.get("part_number"), "pd": order.get("part_description"),
             "sn": order.get("serial_number"), "dp": order.get("depot"),
             "fd": order.get("failure_details"), "ai": order.get("additional_info"), "by": submitted_by})


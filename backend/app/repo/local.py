"""SQLite implementation of repo.base.Repo (file: backend/.data/app.db). Reports are stored FULL.

SqlRepo holds the SQL shared with repo/databricks.py: same table names as Delta (ARCHITECTURE.md §6),
named `:param` placeholders (both sqlite3 and databricks-sql-connector accept them), and no upserts
(create_order inserts the row; save_report updates it).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path

DDL = {
    "app_users": "email STRING, name STRING, role STRING, org STRING",
    "app_orders": "order_id STRING, submitted_by STRING, order_json STRING, created_at STRING",
    "gold_triage_reports": "order_id STRING, status STRING, confidence_score DOUBLE, "
                           "confidence_reasons STRING, report_json STRING, trace_id STRING, "
                           "created_at STRING, updated_at STRING",
    "gold_review_feedback": "order_id STRING, decision STRING, corrected_areas STRING, "
                            "corrected_causes STRING, corrected_parts STRING, notes STRING, "
                            "reviewer STRING, reviewed_at STRING",
    "app_chat_messages": "order_id STRING, user_email STRING, id STRING, message_json STRING, created_at STRING",
    "gold_bench_evidence": "order_id STRING, source STRING, measurement STRING, value DOUBLE, unit STRING, "
                           "spec_min DOUBLE, spec_max DOUBLE, `pass` BOOLEAN, captured_at STRING",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _j(v) -> str:
    return json.dumps(v, default=str)


class SqlRepo:
    def t(self, name: str) -> str:
        return name

    def _exec(self, sql: str, params: dict | None = None) -> list[dict]:
        raise NotImplementedError

    # users
    def get_user(self, email):
        rows = self._exec(f"SELECT email, name, role, org FROM {self.t('app_users')} WHERE email = :e", {"e": email})
        return rows[0] if rows else None

    def user_for_role(self, role):
        from app.repo.seed import DEMO_USERS
        if user := self.get_user(DEMO_USERS.get(role, "")):
            return user
        rows = self._exec(f"SELECT email, name, role, org FROM {self.t('app_users')} WHERE role = :r "
                          "ORDER BY email LIMIT 1", {"r": role})
        return rows[0]

    def add_user(self, user: dict) -> None:
        if not self.get_user(user["email"]):
            self._exec(f"INSERT INTO {self.t('app_users')} VALUES (:email, :name, :role, :org)", user)

    # orders
    def create_order(self, order, submitted_by, report):
        oid = report["order_id"]
        self._exec(f"INSERT INTO {self.t('app_orders')} VALUES (:o, :s, :j, :c)",
                   {"o": oid, "s": submitted_by, "j": _j(order), "c": report["created_at"]})
        self._exec(f"INSERT INTO {self.t('gold_triage_reports')} VALUES (:o, :st, :cs, :cr, :rj, :tr, :c, :u)",
                   {"o": oid, **self._report_cols(report), "c": report["created_at"]})

    @staticmethod
    def _report_cols(report: dict) -> dict:
        conf = report.get("confidence") or {}
        return {"st": report["status"], "cs": conf.get("score"), "cr": _j(conf.get("reasons") or []),
                "rj": _j(report), "tr": report.get("trace_id"), "u": report["updated_at"]}

    def _orders(self, where: str = "", params: dict | None = None) -> list[dict]:
        rows = self._exec(
            f"SELECT o.submitted_by, o.order_json, r.report_json FROM {self.t('app_orders')} o "
            f"JOIN {self.t('gold_triage_reports')} r ON r.order_id = o.order_id {where} "
            "ORDER BY r.created_at DESC", params)
        return [{"submitted_by": r["submitted_by"], "order": json.loads(r["order_json"]),
                 "report": json.loads(r["report_json"])} for r in rows]

    def get_order(self, order_id):
        rows = self._orders("WHERE o.order_id = :o", {"o": order_id})
        return rows[0] if rows else None

    def list_orders(self, submitted_by=None):
        if submitted_by is None:
            return self._orders()
        return self._orders("WHERE o.submitted_by = :s", {"s": submitted_by})

    def save_report(self, order_id, report):
        self._exec(f"UPDATE {self.t('gold_triage_reports')} SET status = :st, confidence_score = :cs, "
                   "confidence_reasons = :cr, report_json = :rj, trace_id = :tr, updated_at = :u "
                   "WHERE order_id = :o", {"o": order_id, **self._report_cols(report)})

    def add_feedback(self, order_id, feedback):
        c = feedback.get("corrections") or {}
        self._exec(f"INSERT INTO {self.t('gold_review_feedback')} VALUES (:o, :d, :a, :c, :p, :n, :r, :t)",
                   {"o": order_id, "d": feedback["decision"], "a": _j(c.get("areas")), "c": _j(c.get("causes")),
                    "p": _j(c.get("parts")), "n": feedback.get("notes"), "r": feedback["reviewer"], "t": _now()})

    def add_evidence(self, order_id, measurements):
        for m in measurements:
            self._exec(f"INSERT INTO {self.t('gold_bench_evidence')} VALUES (:o, :s, :n, :v, :u, :mn, :mx, :p, :t)",
                       {"o": order_id, "s": m.get("source"), "n": m["name"], "v": m["value"], "u": m["unit"],
                        "mn": m.get("spec_min"), "mx": m.get("spec_max"), "p": m.get("pass"), "t": _now()})

    # chat
    def chat_history(self, order_id, email):
        rows = self._exec(f"SELECT message_json FROM {self.t('app_chat_messages')} "
                          "WHERE order_id = :o AND user_email = :e ORDER BY created_at, id",
                          {"o": order_id, "e": email})
        return [json.loads(r["message_json"]) for r in rows]

    def add_chat(self, order_id, email, message):
        self._exec(f"INSERT INTO {self.t('app_chat_messages')} VALUES (:o, :e, :i, :j, :c)",
                   {"o": order_id, "e": email, "i": message["id"], "j": _j(message),
                    "c": message.get("created_at") or _now()})

    # setup
    def is_empty(self) -> bool:
        return not self._exec(f"SELECT email FROM {self.t('app_users')} LIMIT 1")


class LocalRepo(SqlRepo):
    def __init__(self, path: Path | None = None, seed: bool = True):
        from app import config
        self.path = Path(path or config.APP_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        for name, cols in DDL.items():
            self._exec(f"CREATE TABLE IF NOT EXISTS {name} ({cols.replace('STRING', 'TEXT')})")
        self._exec("CREATE UNIQUE INDEX IF NOT EXISTS ux_orders ON app_orders(order_id)")
        self._exec("CREATE UNIQUE INDEX IF NOT EXISTS ux_reports ON gold_triage_reports(order_id)")
        if seed and self.is_empty():
            from app.repo.seed import seed_demo
            seed_demo(self)

    def _exec(self, sql, params=None):
        with self._lock, closing(sqlite3.connect(self.path)) as con, con:
            con.row_factory = sqlite3.Row
            cur = con.execute(sql, params or {})
            return [dict(r) for r in cur.fetchall()] if cur.description else []


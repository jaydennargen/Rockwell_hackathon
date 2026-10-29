"""StatsRepo: where gold stats come from. Same table and column names locally (SQLite gold.db from
scripts/build_local_gold.py) and in Delta (databricks/ notebooks).

    gold_family_stats  product_family, n_labeled, cause_dist, area_dist, top_cause, top_cause_share,
                       npf_rate, median_tat
    gold_part_freq     product_family, cause_category, part, count, freq
    silver_repairs     order_id, serial_number, received_date, cause_category[], ...

Maps/arrays are JSON strings in SQLite and native types in Delta; _obj() accepts both.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional, Protocol

GOLD_TABLES = ("gold_family_stats", "gold_part_freq", "gold_repeat_returns", "gold_depot_patterns",
               "silver_repairs", "silver_manual_sops")


class StatsRepo(Protocol):
    def family_stats(self, family: str) -> Optional[dict]: ...
    def part_freq(self, family: str, cause: str, k: int = 3) -> list[dict]: ...
    def unit_history(self, serial: str) -> list[dict]: ...          # newest first
    def query(self, sql: str) -> tuple[list[str], list[tuple]]: ...  # pre-validated read-only SQL


def _obj(v):
    if v is None:
        return None
    if isinstance(v, (bytes, str)):
        return json.loads(v)
    if hasattr(v, "tolist"):
        return v.tolist()
    return dict(v) if hasattr(v, "items") else list(v)


class _SqlStats:
    def _rows(self, sql: str, params: dict) -> list[dict]:
        raise NotImplementedError

    def t(self, name: str) -> str:
        return name

    def family_stats(self, family):
        rows = self._rows(f"SELECT * FROM {self.t('gold_family_stats')} WHERE product_family = :f", {"f": family})
        if not rows:
            return None
        r = dict(rows[0])
        r["cause_dist"] = _obj(r.get("cause_dist")) or {}
        r["area_dist"] = _obj(r.get("area_dist")) or {}
        return r

    def part_freq(self, family, cause, k=3):
        rows = self._rows(
            f"SELECT part, count, freq FROM {self.t('gold_part_freq')} "
            f"WHERE product_family = :f AND cause_category = :c ORDER BY freq DESC, count DESC LIMIT {int(k)}",
            {"f": family, "c": cause})
        return [{"part": r["part"], "freq": round(float(r["freq"]), 3),
                 "n": round(r["count"] / r["freq"]) if r["freq"] else 0} for r in rows]

    def unit_history(self, serial):
        rows = self._rows(
            f"SELECT order_id, received_date, cause_category FROM {self.t('silver_repairs')} "
            f"WHERE serial_number = :s AND received_date IS NOT NULL ORDER BY received_date DESC LIMIT 20",
            {"s": serial})
        return [{"order_id": r["order_id"], "date": str(r["received_date"])[:10],
                 "causes": [c for c in (_obj(r["cause_category"]) or []) if c != "update_notice"]}
                for r in rows]


class LocalStatsRepo(_SqlStats):
    """backend/.data/gold.db. If the file doesn't exist yet, every lookup is empty (and triage escalates)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _connect(self):
        con = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _rows(self, sql, params):
        if not self.available:
            return []
        with self._connect() as con:
            return [dict(r) for r in con.execute(sql, params)]

    def query(self, sql):
        if not self.available:
            raise RuntimeError("Local gold.db not built yet (scripts/build_local_gold.py).")
        with self._connect() as con:
            cur = con.execute(sql)
            return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]


class DatabricksStatsRepo(_SqlStats):
    """Delta tables in {UC_CATALOG}.{UC_SCHEMA} through a SQL warehouse."""

    def __init__(self, host: str, http_path: str, token: str, catalog: str, schema: str):
        self.conn_args = {"server_hostname": host.replace("https://", "").rstrip("/"),
                          "http_path": http_path, "access_token": token}
        self.prefix = f"{catalog}.{schema}"

    def t(self, name):
        return f"{self.prefix}.{name}"

    def _cursor_rows(self, sql, params):
        from databricks import sql as dbsql
        with dbsql.connect(**self.conn_args) as con, con.cursor() as cur:
            cur.execute(sql, params or None)
            cols = [d[0] for d in cur.description]
            return cols, [tuple(r) for r in cur.fetchall()]

    def _rows(self, sql, params):
        cols, rows = self._cursor_rows(sql, params)
        return [dict(zip(cols, r)) for r in rows]

    def query(self, sql):
        return self._cursor_rows(sql, {})


class MemoryStatsRepo:
    """Dict-backed stats for tests and scripts/eval_holdout.py (stats computed from the train split)."""

    def __init__(self, families: dict, parts: dict, history: dict):
        self.families, self.parts, self.history = families, parts, history

    def family_stats(self, family):
        return self.families.get(family)

    def part_freq(self, family, cause, k=3):
        return self.parts.get((family, cause), [])[:k]

    def unit_history(self, serial):
        return self.history.get(serial, [])

    def query(self, sql):
        raise RuntimeError("SQL is not available on the in-memory stats repo.")


_stats = None


def get_stats_repo():
    global _stats
    if _stats is None:
        from app import config
        if config.DATA_BACKEND == "databricks":
            _stats = DatabricksStatsRepo(config.DATABRICKS_HOST, config.DATABRICKS_HTTP_PATH,
                                         config.DATABRICKS_TOKEN, config.UC_CATALOG, config.UC_SCHEMA)
        else:
            _stats = LocalStatsRepo(config.GOLD_DB)
    return _stats

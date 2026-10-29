"""Testbench: run a file of test orders through the live triage pipeline and grade each one PASS/FAIL.

Used by scripts/testbench.py (CLI) and tests/test_triage_testbench.py (pytest picks up tests/cases/).

Case file formats (detected from the columns):
  * Test-case table (.csv / .xlsx / .json / SQLite table `test_cases`):
        case_id, catalog, failure_details, part_description, serial_number, received_date, depot,
        expected_cause, expected_area, expected_status, min_confidence, max_confidence, notes
    Only `catalog` and `failure_details` are required. Every `expected_*` / `*_confidence` column is
    optional and only checked when filled in. Expected causes/areas take category names
    (wear_out, fan_cooling, ...) or raw SAP strings ("Worn / End of Life"); separate several with `|`.
  * SAP extract (.csv / .xlsx with "Failure Details", "Probable Cause Code", "Affected Areas", ...):
    expected cause/area come from the technician's labels via the same mapping as gold.py.
  * gold.db-shaped SQLite (table `silver_repairs`): labeled rows, same as the SAP extract.

History (the gold stats the pipeline scores against) comes from --history (an SAP extract or a
gold.db), with the test orders removed so they can't leak into their own prediction, or from the
local gold.db, or is empty.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.schemas import TriageReport
from triage.gold import AREA_MAP, CAUSE_MAP, COMPLETE, build_gold, map_area, map_cause, memory_stats, to_silver
from triage.stats_repo import LocalStatsRepo, MemoryStatsRepo

CAUSES = {c for c, _ in CAUSE_MAP}
AREAS = {c for c, _, _ in AREA_MAP} | {"other"}
STATUSES = {"AUTO_RELEASED", "NEEDS_REVIEW"}
LIST_COLS = ("cause_raw", "cause_category", "area_detail", "area_category", "parts")

# Accepted spellings for test-case columns -> canonical name
ALIASES = {
    "id": "case_id", "test_id": "case_id", "name": "case_id",
    "failure_text": "failure_details", "failure_description": "failure_details", "text": "failure_details",
    "description": "part_description", "serial": "serial_number",
    "cause": "expected_cause", "expected_causes": "expected_cause",
    "area": "expected_area", "expected_areas": "expected_area",
    "status": "expected_status",
}


@dataclass
class Case:
    case_id: str
    order: dict
    expect: dict          # causes[], areas[], status, min_confidence, max_confidence
    notes: str = ""


@dataclass
class Check:
    name: str
    passed: bool
    expected: str
    got: str


@dataclass
class Result:
    case: Case
    checks: list[Check] = field(default_factory=list)
    error: str | None = None
    report: dict | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.passed for c in self.checks)


# ---------------------------------------------------------------- loading

def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def _str(v) -> str | None:
    if _blank(v):
        return None
    s = str(v).strip()
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


def _labels(v, kind: str) -> list[str]:
    """'wear_out | Worn / End of Life' -> ['wear_out']. Raw SAP strings go through the gold.py mapping."""
    if _blank(v):
        return []
    known = CAUSES if kind == "cause" else AREAS
    out = []
    for part in re.split(r"[|;]", str(v)):
        p = part.strip()
        if not p:
            continue
        cat = p.lower() if p.lower() in known else (map_cause(p) if kind == "cause" else map_area(p))
        if cat is None or cat not in known:
            raise ValueError(f"unknown {kind} {p!r}; use one of {sorted(known)}")
        out.append(cat)
    return list(dict.fromkeys(out))


def _float(v) -> float | None:
    return None if _blank(v) else float(v)


def _read_table(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if ext == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return pd.DataFrame(data["cases"] if isinstance(data, dict) else data)
    if ext in (".db", ".sqlite", ".sqlite3"):
        with sqlite3.connect(path) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for t in ("test_cases", "silver_repairs"):
                if t in tables:
                    df = pd.read_sql(f"SELECT * FROM {t}", con)
                    df.attrs["table"] = t
                    return df
        raise ValueError(f"{path}: no `test_cases` or `silver_repairs` table")
    raise ValueError(f"{path}: unsupported file type {ext} (use .csv, .xlsx, .json, or .db)")


def _is_sap(df: pd.DataFrame) -> bool:
    return "Failure Details" in df.columns and "Catalog" in df.columns


def _load_silver_db(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in LIST_COLS:
        if c in df.columns:
            df[c] = df[c].map(lambda v: json.loads(v) if isinstance(v, str) else (v or []))
    df["received_date"] = pd.to_datetime(df["received_date"], errors="coerce").dt.date
    df["is_labeled"] = df["is_labeled"].astype(bool)
    return df


def sap_to_silver(df: pd.DataFrame) -> pd.DataFrame:
    """SAP extract -> silver. Rows without an SAP Status column are treated as complete."""
    if "SAP Status" not in df.columns:
        df = df.assign(**{"SAP Status": COMPLETE})
    return to_silver(df)


def _silver_cases(silver: pd.DataFrame) -> list[Case]:
    cases = []
    for r in silver[silver["is_labeled"]].to_dict("records"):
        num, line = r["order_id"].rsplit("-", 1)
        cases.append(Case(
            case_id=r["order_id"],
            order={"order_number": num, "line_number": int(line), "catalog": r["catalog"],
                   "part_number": _str(r.get("part_number")) or "",
                   "part_description": _str(r.get("part_description")) or "",
                   "serial_number": _str(r.get("serial_number")), "depot": _str(r.get("depot")),
                   "failure_details": _str(r.get("failure_text_raw")) or "",
                   "received_date": None if _blank(r.get("received_date")) else str(r["received_date"])},
            expect={"causes": [c for c in r["cause_category"] if c != "update_notice"],
                    "areas": list(r["area_category"]), "status": None,
                    "min_confidence": None, "max_confidence": None},
        ))
    return cases


def _table_cases(df: pd.DataFrame) -> list[Case]:
    df = df.rename(columns=lambda c: str(c).strip().lower().replace(" ", "_"))
    df = df.rename(columns={k: v for k, v in ALIASES.items() if k in df.columns and v not in df.columns})
    missing = {"catalog", "failure_details"} - set(df.columns)
    if missing:
        raise ValueError(f"test-case table is missing column(s): {sorted(missing)}")
    cases = []
    for i, r in enumerate(df.to_dict("records"), start=1):
        row = f"row {i}"
        try:
            if not _str(r.get("catalog")):
                raise ValueError("catalog is empty")
            status = _str(r.get("expected_status"))
            if status:
                status = status.upper()
                if status not in STATUSES:
                    raise ValueError(f"expected_status must be one of {sorted(STATUSES)}, got {status!r}")
            case_id = _str(r.get("case_id")) or f"case-{i:03d}"
            order_number = _str(r.get("order_number")) or f"TB{i:06d}"
            cases.append(Case(
                case_id=case_id,
                order={"order_number": order_number, "line_number": int(float(_str(r.get("line_number")) or 1000)),
                       "catalog": _str(r["catalog"]) or "", "part_number": _str(r.get("part_number")) or "",
                       "part_description": _str(r.get("part_description")) or "",
                       "serial_number": _str(r.get("serial_number")), "depot": _str(r.get("depot")),
                       "failure_details": _str(r.get("failure_details")) or "",
                       "received_date": _str(r.get("received_date"))},
                expect={"causes": _labels(r.get("expected_cause"), "cause"),
                        "areas": _labels(r.get("expected_area"), "area"), "status": status,
                        "min_confidence": _float(r.get("min_confidence")),
                        "max_confidence": _float(r.get("max_confidence"))},
                notes=_str(r.get("notes")) or "",
            ))
        except ValueError as e:
            raise ValueError(f"{row}: {e}") from None
    return cases


def load_cases(path: str | Path) -> list[Case]:
    path = Path(path)
    df = _read_table(path)
    if df.attrs.get("table") == "silver_repairs":
        return _silver_cases(_load_silver_db(df))
    if _is_sap(df):
        return _silver_cases(sap_to_silver(df))
    return _table_cases(df)


# ---------------------------------------------------------------- history

def load_history_silver(path: str | Path) -> pd.DataFrame:
    df = _read_table(Path(path))
    if df.attrs.get("table") == "silver_repairs":
        return _load_silver_db(df)
    if _is_sap(df):
        return sap_to_silver(df)
    raise ValueError(f"{path}: history must be an SAP extract (.xlsx/.csv) or a gold.db with silver_repairs")


def build_stats(history: str | Path | None, cases: list[Case], gold_db: Path | None):
    """Returns (stats repo, description). Test orders are dropped from --history to avoid leakage."""
    if history:
        silver = load_history_silver(history)
        ids = {f"{c.order['order_number']}-{c.order['line_number']}" for c in cases}
        before = len(silver)
        silver = silver[~silver["order_id"].isin(ids)].reset_index(drop=True)
        dropped = before - len(silver)
        desc = f"{history} ({len(silver)} rows" + (f", {dropped} test orders removed)" if dropped else ")")
        return memory_stats(silver, build_gold(silver)), desc
    if gold_db and Path(gold_db).exists():
        return LocalStatsRepo(Path(gold_db)), f"{gold_db} (test orders are NOT removed; pass --history to avoid leakage)"
    return MemoryStatsRepo({}, {}, {}), "none (empty history: most orders will escalate)"


# ---------------------------------------------------------------- grading

def _fmt(xs) -> str:
    return "|".join(xs) if xs else "-"


def grade(case: Case, report: dict, match: str = "top") -> list[Check]:
    checks = []
    try:
        TriageReport.model_validate(report)
        checks.append(Check("schema", True, "valid TriageReport", "valid"))
    except Exception as e:  # pydantic ValidationError
        checks.append(Check("schema", False, "valid TriageReport", str(e).splitlines()[0]))

    ok = report.get("procedure", {}).get("synthetic") is True and report.get("pending_sections") == ["cleaning", "testing"]
    checks.append(Check("invariants", ok, "synthetic manual + cleaning/testing pending",
                        "ok" if ok else "missing synthetic flag or pending_sections"))

    pred = report.get("predicted") or {}
    for key, kind, got in (("causes", "cause", pred.get("causes") or []),
                           ("areas", "area", [a["category"] for a in pred.get("areas") or []])):
        want = case.expect[key]
        if not want:
            continue
        hit = (got[:1] and got[0] in want) if match == "top" else any(g in want for g in got)
        checks.append(Check(kind, bool(hit), _fmt(want), _fmt(got)))

    if case.expect["status"]:
        checks.append(Check("status", report["status"] == case.expect["status"], case.expect["status"], report["status"]))

    score = (report.get("confidence") or {}).get("score")
    lo, hi = case.expect["min_confidence"], case.expect["max_confidence"]
    if lo is not None or hi is not None:
        ok = score is not None and (lo is None or score >= lo) and (hi is None or score <= hi)
        checks.append(Check("confidence", ok, f"{lo if lo is not None else ''}..{hi if hi is not None else ''}", str(score)))
    return checks


def run_case(case: Case, stats, llm, match: str = "top") -> Result:
    from triage.pipeline import triage
    try:
        report = triage(dict(case.order), stats=stats, llm=llm)
    except Exception as e:
        return Result(case, error=f"{type(e).__name__}: {e}")
    return Result(case, checks=grade(case, report, match), report=report)


def results_table(results: list[Result]) -> pd.DataFrame:
    rows = []
    for r in results:
        rep = r.report or {}
        pred = rep.get("predicted") or {}
        row = {"case_id": r.case.case_id, "result": "PASS" if r.passed else "FAIL",
               "status": rep.get("status"), "confidence": (rep.get("confidence") or {}).get("score"),
               "predicted_causes": _fmt(pred.get("causes") or []),
               "predicted_areas": _fmt([a["category"] for a in pred.get("areas") or []]),
               "expected_causes": _fmt(r.case.expect["causes"]), "expected_areas": _fmt(r.case.expect["areas"]),
               "expected_status": r.case.expect["status"] or "",
               "failed_checks": ", ".join(c.name for c in r.checks if not c.passed) or ("error" if r.error else ""),
               "error": r.error or "", "notes": r.case.notes}
        rows.append(row)
    return pd.DataFrame(rows)

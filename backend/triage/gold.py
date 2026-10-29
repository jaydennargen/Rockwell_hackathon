"""SAP extract -> silver_repairs -> gold stats (docs/databricks_backend_spec.md §2-§3).

Used by scripts/build_local_gold.py (writes gold.db) and scripts/eval_holdout.py (stats from the
train split only). The Databricks notebooks must produce the same tables and columns.
"""
from __future__ import annotations

import re

import pandas as pd

from triage.stats_repo import MemoryStatsRepo
from triage.tools import clean_text, product_family

COMPLETE = "Order Complete"

# SAP extract column -> silver column. Optional columns are skipped if missing.
COLUMNS = {
    "Order Number": "order_number", "Line Number": "line_number", "Catalog": "catalog",
    "Part Number": "part_number", "Part Description": "part_description", "Serial Number": "serial_number",
    "Depot": "depot", "SAP Status": "sap_status", "Submit Date": "submit_date",
    "Received Date": "received_date", "Vendor Ship Date": "ship_date", "Net Price": "net_price",
    "Failure Details": "failure_text_raw", "Probable Cause Code": "cause_raw_str",
    "Affected Areas": "area_raw_str", "Parts Replaced": "parts_raw",
}

# §2 cause mapping, checked in order (contains, case-insensitive)
CAUSE_MAP = [
    ("update_notice", ("update -", "update-", "engineering change")),
    ("no_problem_found", ("no problem found",)),
    ("wear_out", ("worn",)),
    ("contamination", ("contamination", "corrosion", "liquid")),
    ("physical_damage", ("physical", "mechanical damage", "tampering", "loose connection")),
    ("configuration_error", ("configuration", "software", "firmware", "calibration", "adjustment")),
    ("external_electrical", ("voltage", "current", "power quality", "load")),
    ("component_failure", ("component failure",)),
]

# §2 area mapping, checked in order
AREA_MAP = [
    ("motor_mechanical", ("motors",), True),
    ("hmi_display", ("touchscreen", "display", "monitor", "crt", "bezel"), False),
    ("fan_cooling", ("fan",), False),
    ("enclosure_wiring", ("cover", "chassis", "cable", "connector"), False),
    ("pcba_circuitry", ("pcba", "circuitry", "bus capacitor", "resistor", "power module", "igbt",
                        "rectifier", "current sensor", "fuse", "power supply"), False),
]


def map_cause(raw: str) -> str | None:
    v = raw.strip().lower()
    for cat, keys in CAUSE_MAP:
        if any(k in v for k in keys):
            return cat
    return None


def map_area(raw: str) -> str:
    v = raw.strip().lower()
    for cat, keys, prefix in AREA_MAP:
        if any(v.startswith(k) if prefix else k in v for k in keys):
            return cat
    return "other"


def split_list(v, sep=",") -> list[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    return [p.strip() for p in str(v).split(sep) if p.strip()]


def clean_part(p: str) -> str:
    return re.sub(r"\s*/\s*Reference Designator\s*:.*$", "", p, flags=re.I).strip()


def to_silver(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns={k: v for k, v in COLUMNS.items() if k in raw.columns})
    for col in COLUMNS.values():
        if col not in df.columns:
            df[col] = None
    df = df[df["sap_status"].astype(str).str.strip() == COMPLETE].copy()
    df["order_number"] = df["order_number"].astype(str).str.split(".").str[0]
    df["line_number"] = pd.to_numeric(df["line_number"], errors="coerce").fillna(1000).astype(int)
    df["order_id"] = df["order_number"] + "-" + df["line_number"].astype(str)
    df["catalog"] = df["catalog"].astype(str)
    df["product_family"] = df["catalog"].map(product_family)
    df["serial_number"] = df["serial_number"].map(lambda v: None if pd.isna(v) else str(v).strip())
    for c in ("submit_date", "received_date", "ship_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    df["tat_days"] = [(s - r).days if pd.notna(s) and pd.notna(r) else None
                      for s, r in zip(df["ship_date"], df["received_date"])]
    cleaned = df["failure_text_raw"].fillna("").astype(str).map(clean_text)
    df["failure_text_clean"] = cleaned.str[0]
    df["text_informative"] = cleaned.str[1]
    df["cause_raw"] = df["cause_raw_str"].map(split_list)
    df["cause_category"] = df["cause_raw"].map(lambda xs: list(dict.fromkeys(c for c in map(map_cause, xs) if c)))
    df["area_detail"] = df["area_raw_str"].map(split_list)
    df["area_category"] = df["area_detail"].map(lambda xs: list(dict.fromkeys(map(map_area, xs))))
    df["parts"] = df["parts_raw"].map(lambda v: [clean_part(p) for p in split_list(v, "^~")])
    df["is_labeled"] = df["cause_category"].map(lambda xs: any(c != "update_notice" for c in xs))
    keep = ["order_id", "catalog", "product_family", "part_number", "part_description", "serial_number",
            "depot", "sap_status", "submit_date", "received_date", "ship_date", "tat_days", "net_price",
            "failure_text_raw", "failure_text_clean", "text_informative", "cause_raw", "cause_category",
            "area_detail", "area_category", "parts", "is_labeled"]
    return df[keep].reset_index(drop=True)


def _share(lists: pd.Series) -> dict:
    n = len(lists)
    counts = pd.Series([x for xs in lists for x in set(xs)]).value_counts()
    return {k: round(v / n, 4) for k, v in counts.items()} if n else {}


def build_gold(silver: pd.DataFrame) -> dict[str, pd.DataFrame]:
    lab = silver[silver["is_labeled"]].copy()
    lab["causes"] = lab["cause_category"].map(lambda xs: [c for c in xs if c != "update_notice"])

    fam_rows = []
    for fam, g in lab.groupby("product_family"):
        cd = _share(g["causes"])
        top = max(cd, key=cd.get) if cd else None
        fam_rows.append({"product_family": fam, "n_labeled": len(g), "cause_dist": cd,
                         "area_dist": _share(g["area_category"]), "top_cause": top,
                         "top_cause_share": cd.get(top, 0.0), "npf_rate": cd.get("no_problem_found", 0.0),
                         "median_tat": pd.to_numeric(g["tat_days"], errors="coerce").median()})
    fam = pd.DataFrame(fam_rows)

    ex = lab[["order_id", "product_family", "causes", "parts"]].explode("causes").dropna(subset=["causes"])
    n_fc = ex.groupby(["product_family", "causes"])["order_id"].nunique().rename("n")
    parts = ex.explode("parts").dropna(subset=["parts"])
    parts = parts[parts["parts"].astype(str).str.len() > 0]
    pc = parts.groupby(["product_family", "causes", "parts"])["order_id"].nunique().rename("count").reset_index()
    pc = pc.join(n_fc, on=["product_family", "causes"])
    pc["freq"] = (pc["count"] / pc["n"]).round(4)
    part_freq = pc.rename(columns={"causes": "cause_category", "parts": "part"})[
        ["product_family", "cause_category", "part", "count", "freq"]]

    s = silver.dropna(subset=["serial_number", "received_date"]).sort_values(["serial_number", "received_date"])
    s = s[s["serial_number"].astype(str).str.len() > 2]
    s["prev_order_id"] = s.groupby("serial_number")["order_id"].shift()
    s["prev_date"] = s.groupby("serial_number")["received_date"].shift()
    s["prev_cause_category"] = s.groupby("serial_number")["cause_category"].shift()
    rep = s.dropna(subset=["prev_order_id"]).copy()
    rep["days_since_prev"] = [(a - b).days for a, b in zip(rep["received_date"], rep["prev_date"])]
    repeat = rep[["serial_number", "order_id", "prev_order_id", "days_since_prev", "prev_cause_category"]]

    dp = lab.explode("causes").dropna(subset=["causes", "received_date"]).copy()
    dp["month"] = dp["received_date"].map(lambda d: d.strftime("%Y-%m"))
    depot = (dp.groupby(["depot", "product_family", "causes", "month"]).size().rename("count").reset_index()
             .rename(columns={"causes": "cause_category"}))
    return {"gold_family_stats": fam, "gold_part_freq": part_freq, "gold_repeat_returns": repeat,
            "gold_depot_patterns": depot}


def memory_stats(silver: pd.DataFrame, gold: dict[str, pd.DataFrame]) -> MemoryStatsRepo:
    families = {r["product_family"]: r for r in gold["gold_family_stats"].to_dict("records")}
    parts: dict = {}
    for r in gold["gold_part_freq"].sort_values(["freq", "count"], ascending=False).to_dict("records"):
        parts.setdefault((r["product_family"], r["cause_category"]), []).append(
            {"part": r["part"], "freq": r["freq"], "n": round(r["count"] / r["freq"]) if r["freq"] else 0})
    history: dict = {}
    s = silver.dropna(subset=["serial_number", "received_date"]).sort_values("received_date", ascending=False)
    for r in s.to_dict("records"):
        history.setdefault(r["serial_number"], []).append(
            {"order_id": r["order_id"], "date": str(r["received_date"]),
             "causes": [c for c in r["cause_category"] if c != "update_notice"]})
    return MemoryStatsRepo(families, parts, history)

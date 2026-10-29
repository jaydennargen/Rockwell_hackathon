"""xlsx + manual -> backend/.data/gold.db with the silver/gold tables named in
docs/databricks_backend_spec.md §3 (category mapping §2, parts split on '^~').

    cd backend && python scripts/build_local_gold.py --xlsx path/to/DDS_SAP_Economy_Repair_Order_Data.xlsx

Lists and maps are stored as JSON strings (Delta uses native arrays/maps; StatsRepo reads both).
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app import config  # noqa: E402
from triage.gold import AREA_MAP, CAUSE_MAP, build_gold, map_area, to_silver  # noqa: E402
from triage.tools import MANUAL  # noqa: E402


def _sqlable(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].map(lambda v: isinstance(v, (list, dict))).any():
            out[c] = out[c].map(lambda v: json.dumps(v) if isinstance(v, (list, dict)) else v)
        elif out[c].dtype == object:
            out[c] = out[c].map(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--out", default=str(config.GOLD_DB))
    args = ap.parse_args()

    raw = pd.read_excel(args.xlsx)
    silver = to_silver(raw)
    gold = build_gold(silver)
    sops = pd.DataFrame([{**s, "synthetic": True} for s in MANUAL["sections"]])
    taxonomy = pd.DataFrame([{"raw_value": k, "field": "cause", "category": c} for c, ks in CAUSE_MAP for k in ks]
                            + [{"raw_value": k, "field": "area", "category": c} for c, ks, _ in AREA_MAP for k in ks])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    with sqlite3.connect(out) as con:
        for name, df in {"silver_repairs": silver, "silver_manual_sops": sops, "silver_taxonomy_map": taxonomy,
                         **gold}.items():
            _sqlable(df).to_sql(name, con, index=False)
        con.execute("CREATE INDEX ix_serial ON silver_repairs(serial_number)")

    lab = silver["is_labeled"]
    raw_areas = [a for xs in silver["area_detail"] for a in xs]
    unmapped = sorted({a for a in raw_areas if a and map_area(a) == "other"})
    print(f"rows {len(raw)} -> complete {len(silver)}; labeled {int(lab.sum())} ({lab.mean():.1%}); "
          f"uninformative text {(~silver['text_informative']).mean():.1%}")
    print(f"area values mapped: {1 - sum(a in unmapped for a in raw_areas) / max(len(raw_areas), 1):.1%}"
          + (f"; unmapped: {unmapped[:15]}" if unmapped else ""))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

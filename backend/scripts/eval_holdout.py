"""Accuracy vs. coverage on the newest 20% of labeled orders (docs/databricks_backend_spec.md §5).

Gold stats are rebuilt from the older 80% only, so the holdout never leaks into the history signal.
Correct = the pipeline's top cause is in the order's true cause_category[].

    cd backend && python scripts/eval_holdout.py --n 300            # FakeLLM (keyword rules)
    cd backend && LLM_MODE=databricks python scripts/eval_holdout.py --n 300
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app import config  # noqa: E402
from triage.gold import build_gold, memory_stats  # noqa: E402
from triage.llm import get_llm  # noqa: E402
from triage.pipeline import triage  # noqa: E402

LIST_COLS = ("cause_raw", "cause_category", "area_detail", "area_category", "parts")


def load_silver(path: Path) -> pd.DataFrame:
    with sqlite3.connect(path) as con:
        df = pd.read_sql("SELECT * FROM silver_repairs", con)
    for c in LIST_COLS:
        df[c] = df[c].map(json.loads)
    df["received_date"] = pd.to_datetime(df["received_date"], errors="coerce").dt.date
    df["is_labeled"] = df["is_labeled"].astype(bool)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=str(config.GOLD_DB))
    ap.add_argument("--n", type=int, default=300, help="holdout orders to run (sampled evenly)")
    args = ap.parse_args()

    silver = load_silver(Path(args.gold))
    lab = silver[silver["is_labeled"]].dropna(subset=["received_date"]).sort_values("received_date")
    cut = int(len(lab) * 0.8)
    train_ids = set(lab["order_id"].iloc[:cut])
    test = lab.iloc[cut:]
    test = test.iloc[:: max(1, len(test) // args.n)][: args.n]
    train_silver = silver[silver["order_id"].isin(train_ids) | ~silver["is_labeled"]]
    stats = memory_stats(train_silver, build_gold(train_silver))
    llm = get_llm()

    rows = []
    for r in test.to_dict("records"):
        order = {"order_number": r["order_id"].rsplit("-", 1)[0], "line_number": int(r["order_id"].rsplit("-", 1)[1]),
                 "catalog": r["catalog"], "part_number": r["part_number"] or "",
                 "part_description": r["part_description"] or "", "serial_number": r["serial_number"],
                 "depot": r["depot"], "failure_details": r["failure_text_raw"] or "",
                 "received_date": str(r["received_date"])}
        rep = triage(order, stats=stats, llm=llm)
        top = (rep["predicted"]["causes"] or [None])[0]
        rows.append({"score": rep["confidence"]["score"], "auto": rep["status"] == "AUTO_RELEASED",
                     "correct": top in r["cause_category"]})
    res = pd.DataFrame(rows)

    print(f"holdout orders: {len(res)} (newest 20% of {len(lab)} labeled; LLM_MODE={config.LLM_MODE})")
    print(f"overall top-cause accuracy: {res['correct'].mean():.1%}\n")
    print(f"{'threshold':>9}  {'coverage':>8}  {'accuracy':>8}")
    for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        cov = res[res["score"] >= t]
        acc = f"{cov['correct'].mean():.1%}" if len(cov) else "-"
        print(f"{t:>9.2f}  {len(cov) / len(res):>8.1%}  {acc:>8}")
    auto = res[res["auto"]]
    print(f"\nwith all routing rules at CONFIDENCE_THRESHOLD={config.CONFIDENCE_THRESHOLD}: "
          f"auto-released {len(auto) / len(res):.1%}, accuracy "
          + (f"{auto['correct'].mean():.1%}" if len(auto) else "-"))


if __name__ == "__main__":
    main()

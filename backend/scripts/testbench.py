"""Testbench: run a test database of orders through the triage pipeline and report PASS/FAIL per case.

    cd backend
    python scripts/testbench.py tests/cases/sample_cases.csv --history tests/cases/sample_history.csv
    python scripts/testbench.py my_cases.xlsx                       # history from backend/.data/gold.db
    python scripts/testbench.py holdout_extract.xlsx --history train_extract.xlsx --match any
    python scripts/testbench.py cases.csv --out results.csv -v      # save a results table, show every check
    LLM_MODE=databricks python scripts/testbench.py cases.csv       # or --llm databricks

Exit code: 0 if the pass rate is at least --min-pass-rate (default 1.0, i.e. every case), 1 if not,
2 if the input couldn't be read. File formats are described in triage/testbench.py and
tests/cases/README.md.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from triage import testbench as tb  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run test orders through the triage pipeline and grade them.")
    ap.add_argument("cases", help="test database: .csv, .xlsx, .json, or .db (test_cases / silver_repairs table)")
    ap.add_argument("--history", help="SAP extract or gold.db to compute repair history from "
                                      "(test orders are removed). Default: backend/.data/gold.db if it exists")
    ap.add_argument("--gold", default=str(config.GOLD_DB), help="gold.db used when --history isn't given")
    ap.add_argument("--no-history", action="store_true", help="run with empty repair history")
    ap.add_argument("--llm", choices=("fake", "databricks"), help="override LLM_MODE")
    ap.add_argument("--threshold", type=float, help="override CONFIDENCE_THRESHOLD for this run")
    ap.add_argument("--match", choices=("top", "any"), default="top",
                    help="cause/area pass if the top prediction (default) or any prediction is expected")
    ap.add_argument("--limit", type=int, help="run only the first N cases")
    ap.add_argument("--only", help="run only cases whose id contains this text")
    ap.add_argument("--min-pass-rate", type=float, default=1.0, help="pass rate needed for exit code 0")
    ap.add_argument("--out", help="write per-case results to .csv or .json")
    ap.add_argument("-v", "--verbose", action="store_true", help="print every check, not only failures")
    args = ap.parse_args(argv)

    if args.llm:
        os.environ["LLM_MODE"] = config.LLM_MODE = args.llm
    if args.threshold is not None:
        config.CONFIDENCE_THRESHOLD = args.threshold

    try:
        cases = tb.load_cases(args.cases)
        if args.only:
            cases = [c for c in cases if args.only in c.case_id]
        if args.limit:
            cases = cases[: args.limit]
        if not cases:
            print("no test cases found (SAP/silver inputs only use labeled rows)", file=sys.stderr)
            return 2
        stats, stats_desc = tb.build_stats(None if args.no_history else args.history, cases,
                                           None if args.no_history else Path(args.gold))
    except (ValueError, FileNotFoundError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    from triage.llm import get_llm
    llm = get_llm()

    print(f"testbench: {len(cases)} cases from {args.cases}")
    print(f"  history:   {stats_desc}")
    print(f"  LLM_MODE={config.LLM_MODE}  CONFIDENCE_THRESHOLD={config.CONFIDENCE_THRESHOLD}  match={args.match}\n")

    results = []
    width = max(len(c.case_id) for c in cases)
    for case in cases:
        r = tb.run_case(case, stats, llm, args.match)
        results.append(r)
        rep = r.report or {}
        score = (rep.get("confidence") or {}).get("score")
        tail = r.error or f"{rep.get('status', ''):<13} conf={score}"
        print(f"{'PASS' if r.passed else 'FAIL'}  {case.case_id:<{width}}  {tail}")
        for c in r.checks:
            if args.verbose or not c.passed:
                print(f"      {'ok ' if c.passed else 'XX '} {c.name:<10} expected {c.expected:<28} got {c.got}")

    n, passed = len(results), sum(r.passed for r in results)
    rate = passed / n
    print(f"\n{passed}/{n} passed ({rate:.1%})")
    names = dict.fromkeys(c.name for r in results for c in r.checks)
    for name in names:
        got = [c.passed for r in results for c in r.checks if c.name == name]
        print(f"  {name:<10} {sum(got)}/{len(got)}")
    errors = sum(r.error is not None for r in results)
    if errors:
        print(f"  {'crashed':<10} {errors}")

    if args.out:
        table = tb.results_table(results)
        out = Path(args.out)
        if out.suffix.lower() == ".json":
            table.to_json(out, orient="records", indent=2)
        else:
            table.to_csv(out, index=False)
        print(f"\nwrote {out}")

    ok = rate >= args.min_pass_rate
    print(f"\n{'PASS' if ok else 'FAIL'} (needed {args.min_pass_rate:.0%})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

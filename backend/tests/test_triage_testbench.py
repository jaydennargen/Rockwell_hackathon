"""Runs every case file in tests/cases/ through the live pipeline (FakeLLM) as part of `pytest`.

To add test cases: drop a `<name>_cases.csv` (or .json / .xlsx) into tests/cases/. If a
`<name>_history.csv` sits next to it, it's used as the repair history; otherwise history is empty.
See tests/cases/README.md for the columns.
"""
from pathlib import Path

import pytest

from triage import testbench as tb
from triage.llm import FakeLLM

CASES_DIR = Path(__file__).parent / "cases"


def _case_files():
    return sorted(p for p in CASES_DIR.glob("*_cases.*") if p.suffix.lower() in (".csv", ".json", ".xlsx"))


def _params():
    out = []
    for path in _case_files():
        history = path.with_name(path.name.split("_cases.")[0] + "_history.csv")
        cases = tb.load_cases(path)
        stats, _ = tb.build_stats(history if history.exists() else None, cases, None)
        out += [pytest.param(c, stats, id=f"{path.stem}:{c.case_id}") for c in cases]
    return out


@pytest.mark.parametrize("case,stats", _params())
def test_case(case, stats):
    r = tb.run_case(case, stats, FakeLLM())
    assert r.error is None, r.error
    failed = [f"{c.name}: expected {c.expected}, got {c.got}" for c in r.checks if not c.passed]
    assert not failed, "; ".join(failed)


def test_failing_case_is_reported():
    case = tb.Case("x", {"order_number": "1", "line_number": 1000, "catalog": "R1394X",
                         "failure_details": "FAN NOISY"},
                   {"causes": ["contamination"], "areas": [], "status": None,
                    "min_confidence": None, "max_confidence": None})
    r = tb.run_case(case, tb.MemoryStatsRepo({}, {}, {}), FakeLLM())
    assert not r.passed and [c.name for c in r.checks if not c.passed] == ["cause"]


def test_bad_label_is_rejected(tmp_path):
    f = tmp_path / "bad_cases.csv"
    f.write_text("catalog,failure_details,expected_cause\nR1394X,FAN NOISY,bogus\n")
    with pytest.raises(ValueError, match="unknown cause"):
        tb.load_cases(f)


def test_sap_extract_as_cases_uses_technician_labels():
    cases = tb.load_cases(CASES_DIR / "sample_history.csv")
    assert cases and cases[0].expect["causes"] == ["wear_out"] and cases[0].expect["areas"] == ["fan_cooling"]

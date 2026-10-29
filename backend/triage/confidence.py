"""Confidence and routing (docs/databricks_backend_spec.md §5).

Hand-weighted for now. The weights are starting values, not measured accuracy; tune them with
scripts/eval_holdout.py, or set CONFIDENCE_MODEL_URI to an MLflow model (see load_model()).

Every predicted cause and area gets its own score and plain-language reasons, so a specialist can
see which part of the prediction is weak. The overall score combines the primary cause and area.
"""
from __future__ import annotations

import math
import os

from triage.tracing import trace

W_BASE, W_TEXT, W_PRIOR, W_AGREE, W_BENCH = 0.10, 0.40, 0.45, 0.05, 0.15
FULL_HISTORY = 200   # labeled orders at which family history counts fully
MIN_HISTORY = 30
REPEAT_DAYS = 180

AREA_WORD = {"cause": "cause", "area": "affected area"}

REASON_NO_TEXT = "The failure description didn't include usable details."
REASON_THIN_HISTORY = "There's little repair history for this product family."
REASON_UNCLEAR = "The failure description and repair history don't point clearly to one cause."
REASON_NO_SOP = "No troubleshooting procedure covers this type of failure yet."


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def category_confidence(kind: str, category: str, ext, hist: dict, bench: int = 0) -> dict:
    """Score one predicted cause or area from measurable signals, with the reasons behind it."""
    dist = hist["cause_dist"] if kind == "cause" else hist["area_dist"]
    n, fam = hist["n_labeled"], hist["product_family"]
    prior = float(dist.get(category, 0.0))
    reliability = min(1.0, math.log1p(n) / math.log1p(FULL_HISTORY)) if n else 0.0
    phrase = ext.evidence.get(category) if ext.text_informative else None
    agrees = kind == "cause" and category == hist.get("top_cause") and n >= MIN_HISTORY

    reasons = []
    if phrase:
        reasons.append(f'The failure description mentions "{phrase}".')
    elif ext.text_informative:
        reasons.append(f"The failure description doesn't point to this {AREA_WORD[kind]}.")
    else:
        reasons.append("No usable failure description, so this comes from repair history only.")
    if n == 0:
        reasons.append(f"No labeled repair history for product family {fam}.")
    else:
        reasons.append(f"{_pct(prior)} of {n} past {fam} repairs had this {AREA_WORD[kind]}.")
        if n < MIN_HISTORY:
            reasons.append(f"Small sample: fewer than {MIN_HISTORY} labeled repairs.")
    if agrees:
        reasons.append("It's the most common cause for this product family.")
    if bench:
        reasons.append("Bench measurements support it." if bench > 0 else "Bench measurements contradict it.")

    score = W_BASE + W_TEXT * bool(phrase) + W_PRIOR * prior * reliability + W_AGREE * agrees + W_BENCH * bench
    return {"kind": kind, "category": category, "score": round(min(max(score, 0.02), 0.98), 2),
            "reasons": reasons}


def overall(categories: list[dict]) -> float:
    """0.6 x primary cause + 0.4 x primary area (the first of each is the primary prediction)."""
    cause = next((c["score"] for c in categories if c["kind"] == "cause"), 0.0)
    area = next((c["score"] for c in categories if c["kind"] == "area"), 0.0)
    return round(0.6 * cause + 0.4 * area, 2)


_model = None


def load_model():
    """Hook for the MLflow logistic regression from databricks/04_confidence_model.
    Returns None (hand-weighted scoring) unless CONFIDENCE_MODEL_URI is set."""
    global _model
    uri = os.environ.get("CONFIDENCE_MODEL_URI")
    if uri and _model is None:
        import mlflow.pyfunc
        _model = mlflow.pyfunc.load_model(uri)
    return _model


@trace
def score(ext, hist: dict, sop_match: bool, bench: int = 0) -> tuple[float, list[dict]]:
    cats = [category_confidence("cause", c, ext, hist, bench if i == 0 else 0) for i, c in enumerate(ext.causes)]
    cats += [category_confidence("area", a.category, ext, hist) for a in ext.areas]
    model = load_model()
    if model is not None:
        import pandas as pd
        feats = pd.DataFrame([{
            "text_informative": int(ext.text_informative),
            "family_top_cause_share": hist["top_cause_share"],
            "log_n_labeled": math.log1p(hist["n_labeled"]),
            "llm_agrees_with_prior": int(bool(ext.causes) and ext.causes[0] == hist.get("top_cause")),
            "sop_match": int(sop_match), "bench_evidence_supports": bench}])
        return round(float(model.predict(feats)[0]), 2), cats
    return overall(cats), cats


def reasons_for(value: float, threshold: float, signals: dict) -> list[str]:
    """The routing rules (spec §5). `signals`: informative, n_labeled, repeat_days, sop_match."""
    informative, n = signals["informative"], signals["n_labeled"]
    reasons = []
    if value < threshold:
        reasons.append(REASON_NO_TEXT if not informative
                       else REASON_THIN_HISTORY if n < MIN_HISTORY else REASON_UNCLEAR)
    if signals["repeat_days"] is not None and signals["repeat_days"] <= REPEAT_DAYS:
        reasons.append(f"This unit was repaired {signals['repeat_days']} days ago and came back.")
    if not informative and n < MIN_HISTORY:
        reasons += [r for r in (REASON_NO_TEXT, REASON_THIN_HISTORY) if r not in reasons]
    if not signals["sop_match"]:
        reasons.append(REASON_NO_SOP)
    return reasons


@trace
def route(value: float, threshold: float, signals: dict) -> tuple[str, list[str]]:
    """NEEDS_REVIEW if any rule fires; every rule adds a reason written for a non-expert."""
    reasons = reasons_for(value, threshold, signals)
    return ("NEEDS_REVIEW" if reasons else "AUTO_RELEASED"), reasons


def bench_support(measurements: list[dict]) -> int:
    """+1 if any measurement is out of spec (the unit shows the fault), -1 if all checked ones pass."""
    checked = [m for m in measurements if m.get("pass") is not None]
    if not checked:
        return 0
    return 1 if any(m["pass"] is False for m in checked) else -1


def rescore_with_evidence(report: dict) -> dict:
    """Apply bench evidence to the primary cause and recompute the overall score. Re-routes between
    NEEDS_REVIEW and AUTO_RELEASED only if no specialist has reviewed the order (ARCHITECTURE.md §8).
    Needs the `signals` the live pipeline stores on the confidence block; mock reports are left as is."""
    conf = report.get("confidence") or {}
    signals = conf.get("signals")
    if not signals:
        return report
    bench = bench_support(report.get("bench_evidence") or [])
    cats = [dict(c) for c in conf["categories"]]
    primary = next((c for c in cats if c["kind"] == "cause"), None)
    if primary is not None:
        delta = W_BENCH * (bench - signals.get("bench", 0))
        primary["score"] = round(min(max(primary["score"] + delta, 0.02), 0.98), 2)
        primary["reasons"] = [r for r in primary["reasons"] if not r.startswith("Bench measurements")]
        if bench:
            primary["reasons"].append("Bench measurements support it." if bench > 0
                                      else "Bench measurements contradict it.")
    value = overall(cats)
    signals = {**signals, "bench": bench}
    reasons = reasons_for(value, conf["threshold"], signals)
    report = {**report, "confidence": {**conf, "score": value, "reasons": reasons, "categories": cats,
                                       "signals": signals}}
    if not report.get("review") and report["status"] in ("NEEDS_REVIEW", "AUTO_RELEASED"):
        report["status"] = "NEEDS_REVIEW" if reasons else "AUTO_RELEASED"
    return report

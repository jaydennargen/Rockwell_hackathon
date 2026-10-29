"""Plain-code pipeline tools: clean_text, product_family, history_lookup, repeat_return_check,
procedure_lookup, parts_predictor, loto_rule. See docs/databricks_backend_spec.md §3-§4."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from triage.tracing import trace

MANUAL = json.loads((Path(__file__).parent / "data" / "manual_sops.json").read_text())
REPEAT_DAYS = 180

_NOISE = re.compile(
    r"\b(?:SERIAL(?: NUMBER)?|S/N|SN)\s*[:=#]\s*\S+"   # Serial Number: X, SN:X, S/N: X
    r"|\bSN\s+\d\S*"                                    # SN 31805783 (not SNAPPED)
    r"|SHIP/END CUSTOMER PO:?\s*\S+"
    r"|\bPO\s*(?:#|NO\.?)?\s*[:=#]\s*\S+|\bPO#\S+"       # PO#=123, PO: 123 (not POWER)
    r"|RAAMP BARCODE\s*=\s*\S+|STORES(?: CODE)?#?\s*=\s*\S+|CAT#\s*=\s*\S+",
    re.I,
)
_EMPTY = re.compile(
    r"NO (REASON|INFORMATION|INFO|SUFFICIENT)|NOT SPECIFIED|UNKNOWN|NOT REPORTED|NO PROVIDED|"
    r"DID NOT IDENTIFY|FAILURE NOT SPECIFIED|NO FAILURE",
    re.I,
)


def clean_text(raw: str) -> tuple[str, bool]:
    """Strip serial/PO/barcode noise. Returns (clean text, informative)."""
    text = _NOISE.sub(" ", raw or "")
    text = re.sub(r"\s+", " ", text).strip(" -/:.'\"")
    informative = len(text) >= 8 and not _EMPTY.search(text)
    return text, informative


def product_family(catalog: str) -> str:
    """Catalog prefix without the leading reman 'R': R2094BM01S/D -> 2094, RMPLB330P -> MPLB,
    AB-CNSB-PROXY -> AB. Must match the Databricks silver notebook."""
    c = (catalog or "").strip().upper()
    if len(c) > 1 and c[0] == "R" and (c[1].isdigit() or c[1].isalpha()):
        c = c[1:]
    m = re.match(r"\d+|[A-Z]+", c)
    return m.group(0) if m else c


@trace
def history_lookup(stats, catalog: str) -> dict:
    fam = product_family(catalog)
    hist = stats.family_stats(fam) or {}
    return {"product_family": fam, "n_labeled": hist.get("n_labeled", 0),
            "cause_dist": hist.get("cause_dist") or {}, "area_dist": hist.get("area_dist") or {},
            "top_cause": hist.get("top_cause"), "top_cause_share": hist.get("top_cause_share", 0.0),
            "npf_rate": hist.get("npf_rate", 0.0)}


@trace
def repeat_return_check(stats, serial: str | None, received: date | str | None) -> dict:
    """Prior repairs of this serial; repeat=True if the newest one is within REPEAT_DAYS."""
    if not serial:
        return {"history": [], "repeat": False, "days": None}
    rec = date.fromisoformat(str(received)) if received else date.today()
    history = [h for h in stats.unit_history(serial) if date.fromisoformat(str(h["date"])) < rec]
    days = (rec - date.fromisoformat(str(history[0]["date"]))).days if history else None
    return {"history": history, "repeat": days is not None and days <= REPEAT_DAYS, "days": days}


@trace
def procedure_lookup(areas: list[str], causes: list[str]) -> tuple[dict, bool]:
    """Exact (area, cause) match in the synthetic manual, else the general protocol."""
    for a in areas:
        for c in causes:
            for s in MANUAL["sections"]:
                if s["area_category"] == a and s["cause_category"] == c:
                    return s, True
    return MANUAL["general"], False


@trace
def parts_predictor(stats, catalog: str, causes: list[str], k: int = 3) -> list[dict]:
    if not causes:
        return []
    return stats.part_freq(product_family(catalog), causes[0], k)


def loto_rule(part_description: str, areas: list[str]) -> bool:
    """Fixed rule, not an LLM output (spec §4): stored energy (drives, power modules, bus caps)
    needs lockout/tagout, and so does any enclosure opening. Every triaged unit gets opened on the
    bench, so this is always True; the arguments stay for when a non-opening path exists."""
    return True

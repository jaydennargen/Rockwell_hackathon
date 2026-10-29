"""LLM protocol + FakeLLM (deterministic, LLM_MODE=fake) + DatabricksLLM (OpenAI-compatible serving
endpoint at {DATABRICKS_HOST}/serving-endpoints, LLM_MODE=databricks)."""
from __future__ import annotations

import json
import re
from typing import Protocol


class LLM(Protocol):
    def complete(self, system: str, user: str, *, task: str, json_mode: bool = False) -> str: ...


# FakeLLM keyword rules: (pattern, category, area detail or symptom phrase)
_AREA_RULES = [
    (r"\bFAN|OVERTEMP|OVER TEMP|OVERHEAT|HEATSINK|COOLING", "fan_cooling", "Component - Fan Assembly"),
    (r"BEARING|ENCODER|RESOLVER|BRAKE|ROTOR|SHAFT|VIBRAT|GRIND|NOISY|NOISE", "motor_mechanical", "Motors - Bearings"),
    (r"TOUCH|SCREEN|DISPLAY|BEZEL|BACKLIGHT|LCD|PIXEL", "hmi_display", "Touchscreen"),
    (r"BOARD|PCB|LOGIC|CAPACITOR|NO INPUT|NO OUTPUT|NO POWER|POWER SUPPLY|IGBT|FUSE|SHORT|\bI/O\b",
     "pcba_circuitry", "PCBA - Other"),
    (r"CABLE|CONNECTOR|CHASSIS|COVER|HOUSING|WIRING", "enclosure_wiring", "Component - Connector"),
]
_DESC_AREAS = [  # fallback from the part description when the text names no area
    (r"SERVO MOTOR|MOTOR", "motor_mechanical", "Motors - Bearings"),
    (r"PANELVIEW|TERMINAL|HMI|DISPLAY", "hmi_display", "Touchscreen"),
    (r"DRIVE|AXIS|MODULE|ADAPTOR|ADAPTER|SUPPLY|I/O|CONTROLLER", "pcba_circuitry", "PCBA - Other"),
]
_CAUSE_RULES = [
    (r"WORN|WEAR|END OF LIFE|NOISY|NOISE|GRIND|BEARING|AGED", "wear_out"),
    (r"WATER|DUST|DIRT|CORRO|OIL|LIQUID|CONTAMIN|RUST", "contamination"),
    (r"BROKE|SNAPPED|CRACK|DROPPED|BENT|DAMAGE|BURNT CONNECTOR|TAMPER|LOOSE", "physical_damage"),
    (r"FIRMWARE|F/W|CONFIG|PARAMETER|CALIBRAT|SOFTWARE|PROGRAM", "configuration_error"),
    (r"VOLTAGE|SURGE|LIGHTNING|POWER QUALITY|SPIKE|OVERCURRENT", "external_electrical"),
    (r"INTERMITTENT|NO FAULT FOUND|WORKS FINE|COULD NOT REPRODUCE", "no_problem_found"),
    (r"FAIL|FAULT|DEAD|BURN|SMOKE|SHORT|NO POWER|NO INPUT|NO OUTPUT|OVERTEMP|ERROR", "component_failure"),
]


def _hits(rules, text):
    out = []
    for rx, *rest in rules:
        m = re.search(rx, text, re.I)
        if m:
            out.append((m.group(0), *rest))
    return out


class FakeLLM:
    """Deterministic stand-in for both pipeline agents. Keyword rules, not a model."""

    def complete(self, system, user, *, task, json_mode=False):
        data = json.loads(user)
        return self._extract(data) if task == "extract" else self._write(data)

    def _extract(self, d):
        text = d["text"] if d["informative"] else ""
        areas, causes, symptoms, evidence = [], [], [], {}
        for phrase, cat, detail in _hits(_AREA_RULES, text):
            if cat not in [a["category"] for a in areas]:
                areas.append({"category": cat, "detail": detail})
                evidence[cat] = phrase.lower()
                symptoms.append(phrase.lower())
        if not areas:
            for phrase, cat, detail in _hits(_DESC_AREAS, d.get("part_description", ""))[:1]:
                areas.append({"category": cat, "detail": detail})
        for phrase, cat in _hits(_CAUSE_RULES, text):
            if cat not in causes and len(causes) < 2:
                causes.append(cat)
                evidence[cat] = phrase.lower()
                symptoms.append(phrase.lower())
        rationale = (f"The failure text mentions {', '.join(dict.fromkeys(symptoms))}." if symptoms
                     else "The failure text gives no usable symptom, so this relies on product history.")
        return json.dumps({"areas": areas, "causes": causes, "symptoms": list(dict.fromkeys(symptoms)),
                           "text_informative": d["informative"], "rationale": rationale,
                           "evidence": evidence})

    def _write(self, f):
        causes = ", ".join(c.replace("_", " ") for c in f["causes"]) or "an undetermined cause"
        areas = ", ".join(a["detail"] for a in f["areas"]) or "an unidentified area"
        parts = [f"Likely {causes} in {areas}."]
        if f.get("repeat_days") is not None and f["repeat_days"] <= 180:
            parts.append(f"This unit was last repaired {f['repeat_days']} days ago.")
        parts.append("Follow the troubleshooting steps below and confirm the fault before replacing parts."
                     if f["sop_match"] else "No matching procedure; use the general protocol.")
        return " ".join(parts)


class DatabricksLLM:
    def __init__(self, host: str, token: str, endpoint: str):
        from openai import OpenAI
        self.client = OpenAI(base_url=f"{host.rstrip('/')}/serving-endpoints", api_key=token)
        self.endpoint = endpoint

    def complete(self, system, user, *, task, json_mode=False):
        kw = {"response_format": {"type": "json_object"}} if json_mode else {}
        r = self.client.chat.completions.create(
            model=self.endpoint, temperature=0, max_tokens=800,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kw)
        return r.choices[0].message.content or ""


def get_llm():
    from app import config
    if config.LLM_MODE == "databricks":
        return DatabricksLLM(config.DATABRICKS_HOST, config.DATABRICKS_TOKEN, config.LLM_ENDPOINT)
    return FakeLLM()

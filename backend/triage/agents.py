"""The 2 pipeline LLM agents. Agent 1 triage_extractor -> Extraction; Agent 2 report_writer -> summary.
Prompts live in triage/prompts/."""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError, field_validator

from app.schemas import Area, CauseCategory
from triage.tracing import trace

PROMPTS = Path(__file__).parent / "prompts"
_CAUSES = set(CauseCategory.__args__)


class Extraction(BaseModel):
    areas: list[Area] = []
    causes: list[CauseCategory] = []
    symptoms: list[str] = []
    text_informative: bool = False
    rationale: str = ""
    evidence: dict[str, str] = {}  # category -> phrase from the text (internal, feeds per-category reasons)

    @field_validator("causes", mode="before")
    @classmethod
    def _known_causes(cls, v):
        return [c for c in (v or []) if c in _CAUSES][:2]

    @field_validator("areas", mode="before")
    @classmethod
    def _known_areas(cls, v):
        valid = set(Area.model_fields["category"].annotation.__args__)
        return [a for a in (v or []) if isinstance(a, dict) and a.get("category") in valid]


def _json_block(s: str) -> str:
    m = re.search(r"\{.*\}", s, re.S)
    return m.group(0) if m else s


@trace
def triage_extractor(llm, text: str, informative: bool, catalog: str, part_description: str) -> Extraction:
    system = (PROMPTS / "extractor.md").read_text()
    user = json.dumps({"text": text, "informative": informative, "catalog": catalog,
                       "part_description": part_description})
    last = None
    for _ in range(2):  # one retry on parse failure
        try:
            ext = Extraction.model_validate_json(_json_block(llm.complete(system, user, task="extract",
                                                                            json_mode=True)))
            if not informative:
                ext.text_informative = False  # the cleaning rule wins over the model
            return ext
        except (ValidationError, ValueError) as e:
            last = e
    raise RuntimeError(f"Extractor returned invalid JSON twice: {last}")


@trace
def report_writer(llm, facts: dict) -> str:
    system = (PROMPTS / "report_writer.md").read_text()
    return llm.complete(system, json.dumps(facts, default=str), task="write").strip()

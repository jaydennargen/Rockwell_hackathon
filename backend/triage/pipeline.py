"""WS4: the live triage pipeline (fixed sequence of steps; 2 LLM agents). See ARCHITECTURE.md §5 and
docs/databricks_backend_spec.md §4-§6.

    clean_text -> triage_extractor (LLM) -> history_lookup -> repeat_return_check
    -> procedure_lookup -> parts_predictor -> confidence.score -> confidence.route
    -> report_writer (LLM) -> full report dict (validates against app.schemas.TriageReport)
"""


def triage(order: dict, stats=None, llm=None) -> dict:
    raise NotImplementedError("WS4: implement the live pipeline; PIPELINE=mock uses triage.mock")

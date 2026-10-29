# Triage testbench cases

`sample_history.csv` is **synthetic** (generated rows shaped like the SAP extract, not real repair data).
It exists so the sample cases have repair history to score against.

## Run

```bash
cd backend
python scripts/testbench.py tests/cases/sample_cases.csv --history tests/cases/sample_history.csv
python scripts/testbench.py my_cases.csv --out results.csv -v
pytest -q tests/test_triage_testbench.py      # runs every *_cases.* file in this folder
```

Exit code 0 = pass, 1 = pass rate below `--min-pass-rate` (default: every case must pass), 2 = bad input.
Run `python scripts/testbench.py -h` for all options (`--llm databricks`, `--threshold`, `--match any`, `--only`, `--limit`).

## Adding cases

Add rows to a CSV (or .xlsx / .json list / SQLite `test_cases` table). Name it `<name>_cases.csv` to have
pytest pick it up; a `<name>_history.csv` next to it (SAP extract columns) becomes its repair history.

| column | required | meaning |
|---|---|---|
| `case_id` | | name shown in the output (defaults to `case-001`, ...) |
| `catalog` | yes | e.g. `R2094BM01S/D` (product family comes from it) |
| `failure_details` | yes | the customer's failure text |
| `part_description`, `serial_number`, `received_date`, `depot`, `order_number`, `line_number` | | as on the order form |
| `expected_cause` | | category (`wear_out`) or raw SAP value (`Worn / End of Life`); several with `\|` |
| `expected_area` | | category (`fan_cooling`) or raw SAP value (`Component - Fan Assembly`); several with `\|` |
| `expected_status` | | `AUTO_RELEASED` or `NEEDS_REVIEW` |
| `min_confidence`, `max_confidence` | | bounds on the overall confidence score |
| `notes` | | free text, copied into the results file |

Blank expected columns aren't checked. Every case is also checked for a valid `TriageReport`, the
synthetic-manual flag, and `pending_sections = ["cleaning", "testing"]`.

Cause/area pass when the **top** prediction is one of the expected values (`--match any`: any prediction).

A full SAP extract (.xlsx/.csv) or a `gold.db` also works as the case file: each labeled row becomes a case,
graded against the technician's cause/area. Pair it with `--history` on a separate (older) extract;
orders that appear in both are removed from the history so they can't predict themselves.

Categories: causes `component_failure configuration_error contamination external_electrical
no_problem_found physical_damage wear_out`; areas `fan_cooling hmi_display motor_mechanical
pcba_circuitry enclosure_wiring other`.

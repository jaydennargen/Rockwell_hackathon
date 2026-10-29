# Failure Analysis Triage: Databricks Backend Spec (v2)

**Owner:** Databricks / data + agents teammate
**Supersedes:** PRD v1 (the changes are listed in §1)
**Use case:** Rockwell Automation Lifecycle Services: Failure Analysis Triage (SHPE AI Hackathon)

The app lets a user submit a SAP repair order. The backend cleans it, triages it, computes a confidence score, and either auto-releases a report modeled on Rockwell's Remanufacturing/Repair Report or escalates it to a human reviewer. A chat panel answers questions about the data and about individual reports. The frontend is being built separately against the API contract in §7, so **the JSON shapes in §7 are frozen**: talk to the frontend owner before changing them.

---

## 0. Data facts (measured on the provided extract)

| Fact | Value | Why it matters |
|---|---|---|
| Rows | 41,504 orders, Jan 2023 – Aug 2026, all "PLS Economy Service" | — |
| `SAP Status` for finished orders | **"Order Complete"** (39,105 rows). The value "Completed" never appears | v1 filter returned 0 rows |
| Completed orders that have a cause/area label | ~39% (15,626 labeled rows in total) | Most of the data is unlabeled; this is our training/eval set |
| `Failure Details` with no usable content ("NO INFORMATION GIVEN", only serial/PO numbers, etc.) | ~38% | Text alone is often not enough, so confidence has to account for it |
| Serial numbers that appear 2+ times | 2,750 serials (6,282 rows); 1,729 returns came within 180 days of the previous one | Repeat-return detection |
| No Problem Found (NPF) | 7.6% of labeled orders, ~$1.0M net price | NPF risk feature |
| Turnaround (Vendor Ship − Received) | median 11 days, p90 84 days | — |
| Site info | **No customer or site column.** `Depot` (24 values) is the only location field | "Across sites" = across depots |
| Delimiters | `Affected Areas` and `Probable Cause Code` are comma-separated and can hold several values; `Parts Replaced` uses `^~` between parts | Treat these as lists |
| Cause strings | Truncated at ~40 chars (e.g. "Tampering / Improper Repair or Modificat") | Map by prefix/contains, not exact match |
| Top returned product | MP-Series 480V AC Rotary Servo Motor (3,606 orders) | Demo examples; hardware roadmap |

**Baseline (quick analysis, please reproduce in Databricks):** predicting the cause from product-family history alone (family = catalog prefix; train on the oldest 80% of labeled orders, test on the newest 20%) is right **51.5%** of the time, vs. 34% for always guessing "component_failure". When the family's history is concentrated (≥70% one cause, ≥30 past orders), accuracy is **73%**, but that covers only **15%** of orders. Confidence-gated routing works; the LLM text features should push both numbers up.

The troubleshooting manual is **synthetic** (it says so itself, and Rockwell's repair team says real procedures are out of scope). Every procedure we show must carry `synthetic: true` and be labeled that way in the UI.

---

## 1. Changes from PRD v1

1. **Status filter:** `SAP Status = 'Order Complete'`, not `'Completed'`.
2. **Cause categories expanded from 4 to 7.** `physical_damage` (11%) and `no_problem_found` (8%) were missing, and NPF risk can't be learned without an NPF label. Causes and areas are **lists**, not single values.
3. **Normalized category columns live in silver.** The parts query matches on `cause_category`, never on the raw `Probable Cause Code`, so the vocabularies line up.
4. **NPF risk = history + text, not an LLM guess.** Use the family's historical NPF rate plus the extractor's text signal.
5. **Lockout/tagout is a fixed rule**, not an LLM output. Severity is advisory only, because there is no ground truth for it.
6. **Model:** use a Llama 3.3 70B–class Foundation Model endpoint. Check the exact endpoint name under Serving; the Llama 3 70B endpoint named in v1 may be retired.
7. **Confidence is computed from measurable signals** (§5), not the LLM's self-reported confidence.

---

## 2. Category mapping (`silver_taxonomy_map`)

Store this as a table (`raw_value`, `field`, `category`) so it can be edited without code changes. Match on the trimmed atomic value after splitting on commas.

### Cause → `cause_category`

| Category | Raw values (contains / prefix) |
|---|---|
| `component_failure` | Component Failure |
| `wear_out` | Worn / End of Life, Worn/End of Serviceable Life |
| `contamination` | Contamination / Environmental, Corrosion / Environmental, Liquid Contamination |
| `physical_damage` | Physical / Mechanical Damage, Tampering / Improper Repair…, Loose Connections |
| `configuration_error` | Configuration Error, Software / Firmware Error, Calibration, Out of Adjustment / Calibration |
| `no_problem_found` | No Problem Found… |
| `external_electrical` | Improper Voltage or Current, Power Quality…, Improper / Faulty Load |
| `update_notice` *(not a failure cause; keep it but don't predict it)* | Update - …, Engineering Change Notice |

### Area → `area_category` (also keep the raw atomic value as `area_detail`)

| Category | Raw values |
|---|---|
| `pcba_circuitry` | `PCBA - *` (except Display Board), `Circuitry - *`, Comms PCBA, Component - Bus Capacitor / Resistors / Power Modules / Power Modules IGBT / Input Bridge Rectifier / Current Sensors / Fuse / Power Supply |
| `fan_cooling` | Component - Fan Assembly / Heatsink Fan / Internal Fan |
| `motor_mechanical` | `Motors - *` (Bearings, Encoder/Resolver, Endbells, Seals, Brake, Rotor, Connector) |
| `hmi_display` | Touchscreen, Component - Display / Monitor / CRT, Component - Bezel Assembly, PCBA - Display Board |
| `enclosure_wiring` | Component - Cover / Chassis / Cable / Connector |
| `other` | anything unmapped (log the unmapped values; aim for >95% coverage) |

The manual's 8 sections only use `pcba_circuitry`, `fan_cooling`, `motor_mechanical`, and `hmi_display`. Any other (area, cause) pair falls back to the general protocol.

---

## 3. Tables (Unity Catalog, Delta)

Suggested catalog/schema: `hackathon.triage`.

### Bronze
- `bronze_sap_repairs`: the xlsx loaded as-is, plus `source` (`historical` | `app_submission`) and `ingested_at`. **App submissions are appended here too**, so there's one master table.
- `bronze_manual_docs`: raw manual text.

### Silver
- `silver_repairs`: one row per order line.
  - `order_id` (= `Order Number` + `-` + `Line Number`), `catalog`, `product_family`, `part_number`, `part_description`, `serial_number`, `depot`, `sap_status`, `submit_date`, `received_date`, `ship_date`, `tat_days`, `net_price`
  - `failure_text_raw`, `failure_text_clean`, `text_informative` (bool)
  - `cause_raw[]`, `cause_category[]`, `area_detail[]`, `area_category[]`
  - `parts[]`: split `Parts Replaced` on `^~`; strip the `/ Reference Designator :…` suffix; keep the full cleaned line (part number + description) as the part key. Part-number formats vary (`24707-171-01`, `PN-140350`, `352440-C01`, `95656502`), so don't over-parse.
  - `is_labeled` (= `cause_category` is non-empty)
- `silver_manual_sops`: `section`, `area_category`, `cause_category`, `steps[]`, `synthetic` = true.
- `silver_taxonomy_map`: §2.

**`product_family`:** the catalog prefix with the leading `R` (reman marker) removed and the series kept, e.g. `R2094BM01S/D` → `2094`, `R1734IB8S/B` → `1734`. Values like `AB-CNSB-PROXY` keep their own token. Check that the family counts look sensible before using them.

**`failure_text_clean`:** remove `Serial Number: …`, `Ship/End Customer PO: …`, `PO#=…`, `S/N …`, barcodes, and `CAT#=…`. `text_informative` = false if what remains is empty, under ~8 chars, or matches NO INFORMATION / NO REASON / NOT SPECIFIED / UNKNOWN / NOT REPORTED / FAILURE NOT SPECIFIED.

### Gold: precomputed stats (nightly job)
- `gold_family_stats`: `product_family`, `n_labeled`, `cause_dist` (map), `top_cause`, `top_cause_share`, `npf_rate`, `median_tat`.
- `gold_part_freq`: `product_family`, `cause_category`, `part`, `count`, `freq` (share of orders in that family+cause that used the part).
- `gold_repeat_returns`: `serial_number`, `order_id`, `prev_order_id`, `days_since_prev`, `prev_cause_category[]`.
- `gold_depot_patterns`: `depot`, `product_family`, `cause_category`, `month`, `count` (feeds the chat).

### Gold: app tables
- `gold_triage_reports`: `order_id`, `status` (`PROCESSING` | `AUTO_RELEASED` | `NEEDS_REVIEW` | `APPROVED` | `EDITED` | `REJECTED`), `confidence_score`, `confidence_reasons[]`, `report_json` (the §7 object as a string), `trace_id`, `created_at`, `updated_at`.
- `gold_review_feedback`: `order_id`, `decision`, `corrected_areas[]`, `corrected_causes[]`, `corrected_parts[]`, `notes`, `reviewer`, `reviewed_at`. **Reviewer corrections count as new labels** in the next confidence-model training run.
- `gold_bench_evidence`: `order_id`, `source`, `measurement`, `value`, `unit`, `spec_min`, `spec_max`, `pass`, `captured_at` (hardware hook; see §8).

---

## 4. Agents and tools

**3 LLM agents. Everything else is plain Python.** The pipeline runs a fixed sequence of steps (no LLM planner), so it is predictable, fast, and fully traced.

| # | Agent | Input → Output | Implementation |
|---|---|---|---|
| 1 | Triage extractor | `failure_text_clean`, `catalog`, `part_description` → `Extraction` | One call, JSON output validated with Pydantic, one retry on parse failure |
| 2 | Report writer | All tool outputs → the report's narrative fields | One call. The prompt says: use only the facts provided; if a field is missing, say so; never claim tests were performed |
| 3 | Analyst (chat) | User question (+ optional `order_id`) → answer, SQL, sources | Genie Conversation API over the gold tables. If unavailable: a tool loop with `run_sql` (read-only, gold tables only), `get_report`, `get_procedure` |

```python
class Extraction(BaseModel):
    areas: list[AreaCategory]          # enum from §2
    causes: list[CauseCategory]        # enum from §2, excluding update_notice
    symptoms: list[str]                # short phrases pulled from the text
    text_informative: bool
    rationale: str                     # 1–2 sentences, shown to the reviewer
```

**Plain-code tools** (the pipeline calls them; Agent 3 can call some of them too):

| Tool | Logic |
|---|---|
| `history_lookup(catalog)` | Read `gold_family_stats` for the product family |
| `repeat_return_check(serial)` | Prior orders for this serial from `silver_repairs`; flag if `days_since_prev ≤ 180` |
| `procedure_lookup(areas, causes)` | Exact match on (area, cause) in `silver_manual_sops`; else return "General Troubleshooting Protocol applies. Proceed with standard electrical/mechanical baseline checks." |
| `parts_predictor(catalog, causes)` | Top 3 parts by `freq` from `gold_part_freq` for family × cause; include `freq` and `n` |
| `confidence_score(...)` | §5 |
| `route(conf, repeat, extraction, sop)` | §5 |
| `loto_rule(part_description, areas)` | true if a drive/power module or the areas include a bus capacitor / power board (stored energy); otherwise true for any enclosure opening. Default to true when unsure |

**Pipeline:**

```python
@mlflow.trace
def triage(order: OrderIn) -> TriageReport:
    clean  = clean_text(order.failure_details)
    ext    = triage_agent(clean, order.catalog, order.part_description)   # Agent 1
    hist   = history_lookup(order.catalog)
    repeat = repeat_return_check(order.serial_number)
    sop    = procedure_lookup(ext.areas, ext.causes)
    parts  = parts_predictor(order.catalog, ext.causes)
    conf   = confidence_score(ext, hist, sop, evidence=get_evidence(order.order_id))
    status = route(conf, repeat, ext, sop)
    report = report_writer(order, ext, hist, repeat, sop, parts, conf)    # Agent 2
    write_gold(order.order_id, status, report)
    return report
```

LLM calls: use Databricks' OpenAI-compatible serving API (`OpenAI(base_url=f"{host}/serving-endpoints", api_key=token)`) or `mlflow.deployments.get_deploy_client("databricks")`; both work. Wrap each tool in `@mlflow.trace` too, so the trace shows every step in the demo.

---

## 5. Confidence and routing

**Features** (one row per prediction):
- `text_informative` (from the cleaning step and Agent 1)
- `family_top_cause_share` and `log(n_labeled)` from `gold_family_stats`
- `llm_agrees_with_prior`: Agent 1's top cause == the family's `top_cause`
- `sop_match` (bool)
- `bench_evidence_supports` (−1 / 0 / +1; 0 when there is no evidence)

**Label:** whether Agent 1's top cause is in the order's true `cause_category[]`.

**Training:**
1. Run Agent 1 in batch over a sample of labeled orders. `ai_query()` in SQL is the easy route; 3–5k rows is enough.
2. Use the same date-based split: train on the older 80%, test on the newer 20%.
3. Fit scikit-learn `LogisticRegression` and log it to MLflow.
4. Plot accuracy vs. coverage across thresholds. Pick the threshold that meets a target accuracy (start at 0.80) and record the auto-release rate it gives. **That pair of numbers goes in the pitch.**

**Routing:** `NEEDS_REVIEW` if any of the following is true, otherwise `AUTO_RELEASED`:
- `score < threshold`
- repeat return within 180 days
- `text_informative == false` and `n_labeled < 30`
- no SOP match

Store every reason that fired in `confidence_reasons[]`; the UI shows them.

**Fallback if time runs short:** a hand-weighted score with the threshold tuned on the holdout. Still report the accuracy-vs-coverage numbers.

---

## 6. Report content

Modeled on the sample Remanufacturing/Repair Report, but this is a **pre-repair triage** report, so it never claims cleaning or tests were done.

1. **Header:** order no., item, part number, catalog, serial, description, depot, date received
2. **Customer input:** cleaned complaint, plus "no usable description provided" when `text_informative` is false
3. **Predicted affected areas** (categories + details)
4. **Predicted probable cause** + rationale
5. **Parts to pre-stage:** top 3 with historical frequency and sample size
6. **Troubleshooting steps:** SOP section, labeled "Synthetic reference manual"; lockout/tagout flag
7. **Unit history:** prior repairs of this serial
8. **NPF risk:** family NPF rate + text signal
9. **Confidence:** score, threshold, reasons
10. **Cleaning / Testing:** "To be completed by technician"

---

## 7. API contract (FastAPI backend, deployed as a Databricks App)

> **Superseded:** the role-aware API in `ARCHITECTURE.md` §4 is now the source of truth. This section is kept for reference only.

The backend reads and writes Delta through `databricks-sql-connector` to a SQL warehouse. `POST /orders` appends to `bronze_sap_repairs`, inserts a `PROCESSING` row in `gold_triage_reports`, runs `triage()` as a background task, and returns immediately. The frontend polls.

```
POST /api/orders               body: OrderIn → {order_id, status}
POST /api/orders/bulk          multipart .xlsx/.csv (same columns as the extract) → {order_ids: []}
GET  /api/orders/{order_id}    → TriageReport
GET  /api/orders?status=NEEDS_REVIEW&limit=50 → [{order_id, catalog, status, confidence_score, created_at}]
POST /api/orders/{order_id}/review   {decision: "approve"|"edit"|"reject", corrections?: {...}, notes?}
POST /api/orders/{order_id}/evidence {source, measurements: [{name, value, unit, spec_min?, spec_max?}]}
POST /api/chat                 {message, order_id?, conversation_id?} → {answer, sql?, sources: [], conversation_id}
```

**OrderIn**

```json
{
  "order_number": "67083053", "line_number": 1000,
  "part_number": "R1394CAM75IH/C", "catalog": "R1394CAM75IH/C",
  "part_description": "MOD AXIS INTL HTSNK 15KW 35.0A CONT",
  "serial_number": "1JAP5JK8", "depot": "P1100",
  "failure_details": "'No reason given - FQA Serial Number: 1JAP5JK8 ...",
  "additional_info": null, "received_date": "2026-08-13"
}
```

**TriageReport**

```json
{
  "order_id": "67083053-1000",
  "status": "NEEDS_REVIEW",
  "confidence": {"score": 0.58, "threshold": 0.70,
                 "reasons": ["uninformative failure text", "repeat return: 142 days"]},
  "header": {"order_number": "67083053", "item": 1000, "part_number": "R1394CAM75IH/C",
             "catalog": "R1394CAM75IH/C", "serial": "1JAP5JK8",
             "description": "MOD AXIS INTL HTSNK 15KW 35.0A CONT",
             "depot": "P1100", "received_date": "2026-08-13"},
  "customer_input": {"text": "No reason given", "informative": false},
  "predicted": {
    "areas": [{"category": "fan_cooling", "detail": "Component - Fan Assembly"},
              {"category": "pcba_circuitry", "detail": "Component - Bus Capacitor"}],
    "causes": ["wear_out"],
    "rationale": "...",
    "npf_risk": {"family_rate": 0.06, "flag": false}
  },
  "parts_to_prestage": [{"part": "306445-FAN,AXL,60X25MM,12VDC,27CFM", "freq": 0.41, "n": 212}],
  "procedure": {"section": 6, "title": "Fan / Cooling - Worn / End of Life",
                "synthetic": true, "loto_required": true, "steps": ["..."]},
  "unit_history": [{"order_id": "...", "date": "2026-03-24", "causes": ["wear_out"]}],
  "bench_evidence": [],
  "narrative": "Technician summary paragraph from Agent 2",
  "trace_id": "tr-...",
  "created_at": "2026-10-29T14:05:00Z"
}
```

Error shape for every endpoint: `{"error": {"code": "string", "message": "string"}}`.

---

## 8. Hardware hook (plan for it now, build it last)

`POST /api/orders/{id}/evidence` and `gold_bench_evidence` let a bench tester attach objective measurements to an order. The stretch demo uses an FPGA (Spartan-7 Urbana) fan tach counter that sends RPM over UART to a small Python bridge, which posts here. A measurement below spec counts as evidence for `fan_cooling` + `wear_out` and feeds `bench_evidence_supports` in §5. Nothing else in the backend depends on it; with no evidence the feature is 0.

Roadmap (slides only): FPGA vibration FFT for servo motor bearings, capacitor ESR measurement for drives, and field-side condition data arriving with the return.

---

## 9. Build order and done criteria

| Step | Done when |
|---|---|
| 1. Bronze + silver + category mapping | `silver_repairs` built; >95% of raw area/cause values mapped; label coverage matches §0 |
| 2. Gold stats tables | Reproduce the §0 baseline (≈51% family-majority accuracy) from `gold_family_stats` |
| 3. Agent 1 + tools + `triage()` | One `Submitted` order goes end to end in a notebook with a full MLflow trace |
| 4. Confidence model | Accuracy-vs-coverage table logged; threshold chosen |
| 5. FastAPI app | All §7 endpoints return the frozen shapes; the frontend switches from mock to live |
| 6. Review loop | Approve/edit writes to `gold_review_feedback`; status updates |
| 7. Chat | Genie space (or fallback agent) answers 5 scripted demo questions |
| 8. Evidence endpoint | Writes `gold_bench_evidence` and re-scores the order |

**Demo test set:** hold out ~20 labeled orders from the most recent month, run them through the app in the demo, and show prediction vs. actual. Pick a mix of auto-released and escalated cases, including at least one repeat return and one uninformative-text order.

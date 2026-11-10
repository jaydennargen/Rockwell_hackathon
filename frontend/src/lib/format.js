const DATE = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
const DATETIME = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export const fmtDate = (v) => (v ? DATE.format(new Date(String(v).length === 10 ? `${v}T12:00:00` : v)) : "—");
export const fmtDateTime = (v) => (v ? DATETIME.format(new Date(v)) : "—");
export const pct = (v) => `${Math.round(v * 100)}%`;
const pad = (n) => String(n).padStart(2, "0");
// MM/DD/YYYY like the SAP repair report
export const fmtSapDate = (v) => {
  if (!v) return "";
  const d = new Date(String(v).length === 10 ? `${v}T12:00:00` : v);
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())}/${d.getFullYear()}`;
};

// cause_category -> SAP "Probable Cause Code" wording (mirrors backend/app/report_pdf.py)
export const CAUSE_SAP = {
  component_failure: "Component Failure",
  wear_out: "Worn / End of Life",
  contamination: "Contamination / Environmental",
  physical_damage: "Physical / Mechanical Damage",
  configuration_error: "Configuration Error",
  no_problem_found: "No Problem Found",
  external_electrical: "Improper Voltage or Current",
};

export const AREA_LABELS = {
  pcba_circuitry: "Circuit boards",
  fan_cooling: "Fan and cooling",
  motor_mechanical: "Motor and mechanical",
  hmi_display: "Display and touchscreen",
  enclosure_wiring: "Enclosure and wiring",
  other: "Other",
};

export const CAUSE_LABELS = {
  component_failure: "Component failure",
  wear_out: "Worn or end of life",
  contamination: "Contamination",
  physical_damage: "Physical damage",
  configuration_error: "Configuration error",
  no_problem_found: "No problem found",
  external_electrical: "External electrical",
};

// status -> visual tone; labels always come from the API (status_label)
export const STATUS_TONE = {
  PROCESSING: "processing",
  AUTO_RELEASED: "ok",
  APPROVED: "ok",
  EDITED: "ok",
  NEEDS_REVIEW: "review",
  REJECTED: "closed",
  FAILED: "failed",
};

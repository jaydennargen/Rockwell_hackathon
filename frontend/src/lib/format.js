const DATE = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
const DATETIME = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export const fmtDate = (v) => (v ? DATE.format(new Date(String(v).length === 10 ? `${v}T12:00:00` : v)) : "—");
export const fmtDateTime = (v) => (v ? DATETIME.format(new Date(v)) : "—");
export const pct = (v) => `${Math.round(v * 100)}%`;

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

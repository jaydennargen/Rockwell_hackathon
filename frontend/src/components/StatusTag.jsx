import { STATUS_TONE } from "../lib/format.js";

// Status pill. Label comes from the API (role-specific).
export default function StatusTag({ status, label }) {
  return <span className={`status-tag tone-${STATUS_TONE[status] || "processing"}`}>{label}</span>;
}

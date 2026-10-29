import { STATUS_TONE } from "../lib/format.js";

// Small luggage-tag shaped status marker. Label comes from the API (role-specific).
export default function StatusTag({ status, label }) {
  return (
    <span className={`status-tag tone-${STATUS_TONE[status] || "processing"}`}>
      <span className="status-tag-hole" aria-hidden="true" />
      {label}
    </span>
  );
}

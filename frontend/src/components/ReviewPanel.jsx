import { useState } from "react";
import * as api from "../api/client.js";
import { AREA_LABELS, CAUSE_LABELS } from "../lib/format.js";

const DECISIONS = [
  ["approve", "Approve"],
  ["edit", "Correct"],
  ["reject", "Reject"],
];

export default function ReviewPanel({ report, onReviewed }) {
  const reviewable = !["PROCESSING", "FAILED"].includes(report.status);
  const [open, setOpen] = useState(!report.review && report.status === "NEEDS_REVIEW");
  const [decision, setDecision] = useState("approve");
  const [causes, setCauses] = useState(report.predicted?.causes || []);
  const [areas, setAreas] = useState(report.predicted?.areas || []);
  const [parts, setParts] = useState((report.parts_to_prestage || []).map((p) => p.part).join("\n"));
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!reviewable) return null;

  if (!open) {
    return (
      <section className="review review-closed">
        <h2>Review</h2>
        <p className="muted">
          {report.review ? `Reviewed (${report.review.decision}).` : "Auto-released. You can still review it."}
        </p>
        <button className="btn-quiet" onClick={() => setOpen(true)}>
          {report.review ? "Review again" : "Review this report"}
        </button>
      </section>
    );
  }

  const toggleCause = (c) => setCauses((cs) => (cs.includes(c) ? cs.filter((x) => x !== c) : [...cs, c]));

  async function submit(e) {
    e.preventDefault();
    if (decision === "reject" && !notes.trim()) return setError("Add a note so the requester knows why.");
    if (decision === "edit" && causes.length === 0) return setError("Pick at least one cause.");
    setBusy(true);
    setError(null);
    try {
      const body = { decision, notes: notes.trim() || null };
      if (decision === "edit")
        body.corrections = {
          causes,
          areas,
          parts: parts.split("\n").map((p) => p.trim()).filter(Boolean),
        };
      const updated = await api.reviewOrder(report.order_id, body);
      setOpen(false);
      onReviewed(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="review" onSubmit={submit}>
      <h2>Review</h2>
      <div className="segmented" role="radiogroup" aria-label="Decision">
        {DECISIONS.map(([v, label]) => (
          <label key={v} className={decision === v ? "on" : ""}>
            <input type="radio" name="decision" value={v} checked={decision === v} onChange={() => setDecision(v)} />
            {label}
          </label>
        ))}
      </div>

      {decision === "edit" && (
        <div className="review-edit">
          <fieldset>
            <legend>Cause</legend>
            <div className="check-grid">
              {Object.entries(CAUSE_LABELS).map(([k, label]) => (
                <label key={k} className="check">
                  <input type="checkbox" checked={causes.includes(k)} onChange={() => toggleCause(k)} />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>Affected areas</legend>
            {areas.map((a, i) => (
              <div className="area-row" key={i}>
                <select
                  aria-label="Area"
                  value={a.category}
                  onChange={(e) => setAreas(areas.map((x, j) => (j === i ? { ...x, category: e.target.value } : x)))}
                >
                  {Object.entries(AREA_LABELS).map(([k, l]) => (
                    <option key={k} value={k}>
                      {l}
                    </option>
                  ))}
                </select>
                <input
                  aria-label="Detail"
                  value={a.detail}
                  onChange={(e) => setAreas(areas.map((x, j) => (j === i ? { ...x, detail: e.target.value } : x)))}
                />
                <button type="button" className="btn-quiet" onClick={() => setAreas(areas.filter((_, j) => j !== i))}>
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              className="btn-quiet"
              onClick={() => setAreas([...areas, { category: "pcba_circuitry", detail: "" }])}
            >
              Add area
            </button>
          </fieldset>
          <label className="field">
            <span>Parts to pre-stage, one per line</span>
            <textarea rows={3} value={parts} onChange={(e) => setParts(e.target.value)} />
          </label>
        </div>
      )}

      <label className="field">
        <span>{decision === "reject" ? "Note to the requester" : "Note (optional)"}</span>
        <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="row-actions">
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Saving" : { approve: "Approve report", edit: "Save corrections", reject: "Reject report" }[decision]}
        </button>
        {report.review && (
          <button type="button" className="btn-quiet" onClick={() => setOpen(false)}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

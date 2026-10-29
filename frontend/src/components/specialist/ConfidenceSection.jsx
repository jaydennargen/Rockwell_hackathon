import { pct } from "../../lib/format.js";
import Section from "../Section.jsx";

export default function ConfidenceSection({ confidence, npf }) {
  const { score, threshold, reasons } = confidence;
  const pass = score >= threshold && reasons.length === 0;
  return (
    <Section title="Confidence" note="Specialists only" tone={pass ? undefined : "review"}>
      <div className="gauge" role="img" aria-label={`Score ${pct(score)}, release threshold ${pct(threshold)}`}>
        <div className="gauge-track">
          <span className="gauge-fill" style={{ width: pct(score) }} />
          <span className="gauge-mark" style={{ left: pct(threshold) }} />
        </div>
        <p className="gauge-legend">
          <strong>{pct(score)}</strong> against a release threshold of {pct(threshold)}
        </p>
      </div>
      {reasons.length > 0 ? (
        <ul className="plain-list">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">No escalation rules fired.</p>
      )}
      {npf && (
        <p className="npf">
          No-problem-found rate for this product family: <strong>{pct(npf.family_rate)}</strong>
          {npf.flag && ". Above normal, so confirm the fault on the bench before replacing parts."}
        </p>
      )}
    </Section>
  );
}

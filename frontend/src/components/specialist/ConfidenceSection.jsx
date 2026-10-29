import { AREA_LABELS, CAUSE_LABELS, pct } from "../../lib/format.js";
import Section from "../Section.jsx";

function Meter({ score, threshold, label }) {
  const low = score < threshold;
  return (
    <div className="meter" role="img" aria-label={`${label}: ${pct(score)}, release threshold ${pct(threshold)}`}>
      <span className={`meter-fill${low ? " is-low" : ""}`} style={{ width: pct(score) }} />
      <span className="meter-mark" style={{ left: pct(threshold) }} />
    </div>
  );
}

// Specialist only: overall confidence, which routing rules fired, and confidence per predicted cause and area.
export default function ConfidenceSection({ confidence, npf }) {
  const { score, threshold, reasons, categories = [] } = confidence;
  const label = (c) => (c.kind === "cause" ? CAUSE_LABELS : AREA_LABELS)[c.category] || c.category;
  return (
    <Section title="AI confidence" note="Specialists only" tone={reasons.length ? "review" : undefined}>
      <div className="conf-overall">
        <p>
          <strong className="conf-num">{pct(score)}</strong> overall
          <span className="muted"> · releases at {pct(threshold)}</span>
        </p>
        <Meter score={score} threshold={threshold} label="Overall" />
      </div>

      <div>
        <h3 className="subhead">{reasons.length ? "Why it was escalated" : "Routing"}</h3>
        {reasons.length > 0 ? (
          <ul className="plain-list">
            {reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No escalation rules fired.</p>
        )}
      </div>

      {categories.length > 0 && (
        <div>
          <h3 className="subhead">By category</h3>
          <ul className="conf-list">
            {categories.map((c) => (
              <li key={c.kind + c.category} className="conf-item">
                <div className="conf-item-head">
                  <span>
                    <span className="conf-kind">{c.kind === "cause" ? "Cause" : "Area"}</span> {label(c)}
                  </span>
                  <strong className={c.score < threshold ? "txt-review" : ""}>{pct(c.score)}</strong>
                </div>
                <Meter score={c.score} threshold={threshold} label={label(c)} />
                <ul className="conf-reasons">
                  {c.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}

      {npf && (
        <p className="npf">
          No-problem-found rate for this product family: <strong>{pct(npf.family_rate)}</strong>
          {npf.flag && ". Confirm the fault on the bench before replacing parts."}
        </p>
      )}
    </Section>
  );
}

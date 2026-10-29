import { AREA_LABELS, CAUSE_LABELS, fmtDate, fmtDateTime } from "../lib/format.js";
import EscalationNotice from "./EscalationNotice.jsx";
import ReportHeader from "./ReportHeader.jsx";
import Section from "./Section.jsx";
import BenchEvidence from "./specialist/BenchEvidence.jsx";
import ConfidenceSection from "./specialist/ConfidenceSection.jsx";
import PartsSection from "./specialist/PartsSection.jsx";

// Data-driven: renders a section only when the API sent that key. The server decides what each role sees.
export default function ReportView({ report }) {
  const r = report;
  const processing = r.status === "PROCESSING";
  return (
    <article className="report">
      <ReportHeader report={r} />
      <div className="sheet">
        {processing && (
          <Section title="Triage in progress">
            <p className="lead">
              Reading the failure description and checking this product's repair history. This page
              updates on its own.
            </p>
          </Section>
        )}
        {r.status === "FAILED" && (
          <Section title="Couldn't process" tone="failed">
            <p className="lead">Triage stopped before a report was produced. A specialist can run it again.</p>
            {r.error && <p className="muted mono-ish">{r.error}</p>}
          </Section>
        )}

        {r.escalation && <EscalationNotice escalation={r.escalation} />}

        {r.review && (
          <Section
            title="Specialist review"
            note={`${r.review.reviewer}, ${fmtDateTime(r.review.reviewed_at)}`}
            tone={r.review.decision === "reject" ? "failed" : "ok"}
          >
            <p className="lead">
              {{ approve: "Report verified as written.", edit: "Report verified with corrections.",
                 reject: "Report not released." }[r.review.decision]}
            </p>
            {r.review.notes && <blockquote className="note-quote">{r.review.notes}</blockquote>}
          </Section>
        )}

        <Section title="Reported failure" note={r.customer_input.informative ? null : "No usable detail"}>
          <p className="customer-text">{r.customer_input.text || "No description provided."}</p>
        </Section>

        {r.summary && (
          <Section title="Summary">
            <p className="lead">{r.summary}</p>
          </Section>
        )}

        {r.predicted && (
          <Section title="Likely cause">
            <p className="cause-line">
              {r.predicted.causes.map((c) => CAUSE_LABELS[c] || c).join(", ")}
            </p>
            <p>{r.predicted.rationale}</p>
            <ul className="area-list">
              {r.predicted.areas.map((a) => (
                <li key={a.category + a.detail}>
                  <span className="area-cat">{AREA_LABELS[a.category] || a.category}</span>
                  <span className="area-detail">{a.detail}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {r.confidence && <ConfidenceSection confidence={r.confidence} npf={r.npf_risk} />}
        {r.parts_to_prestage && <PartsSection parts={r.parts_to_prestage} />}

        {r.procedure && (
          <Section
            title="Troubleshooting"
            note={r.procedure.section ? `Section ${r.procedure.section}: ${r.procedure.title}` : r.procedure.title}
          >
            {r.procedure.loto_required && (
              <p className="loto">Lock out and discharge the unit before opening the enclosure.</p>
            )}
            <ol className="steps">
              {r.procedure.steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
            {r.procedure.synthetic && (
              <p className="fineprint">
                From the synthetic reference manual provided for this hackathon. Not official Rockwell
                Automation documentation.
              </p>
            )}
          </Section>
        )}

        {r.bench_evidence?.length > 0 && <BenchEvidence items={r.bench_evidence} />}

        {r.unit_history && (
          <Section title="Unit history">
            {r.unit_history.length === 0 ? (
              <p className="muted">No earlier repairs on record for this serial number.</p>
            ) : (
              <ul className="plain-list">
                {r.unit_history.map((h) => (
                  <li key={h.order_id}>
                    {fmtDate(h.date)}: order {h.order_id},{" "}
                    {h.causes.map((c) => CAUSE_LABELS[c] || c).join(", ")}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        )}

        {r.pending_sections?.length > 0 && !processing && (
          <Section title="Cleaning and testing">
            <p className="muted">Recorded by the technician after the repair.</p>
          </Section>
        )}
      </div>
    </article>
  );
}

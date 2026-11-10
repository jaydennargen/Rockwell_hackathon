import { useState } from "react";
import { BRAND } from "../lib/brand.js";
import { AREA_LABELS, CAUSE_LABELS, fmtDate, fmtDateTime } from "../lib/format.js";
import DownloadPdfButton from "./DownloadPdfButton.jsx";
import EscalationNotice from "./EscalationNotice.jsx";
import RepairReport from "./RepairReport.jsx";
import ReportHeader from "./ReportHeader.jsx";
import Section from "./Section.jsx";
import BenchEvidence from "./specialist/BenchEvidence.jsx";
import ConfidenceSection from "./specialist/ConfidenceSection.jsx";
import PartsSection from "./specialist/PartsSection.jsx";

const TABS = [
  ["triage", `${BRAND.name} triage`],
  ["report", "Repair report"],
];

// Data-driven: renders a section only when the API sent that key. The server decides what each role sees.
function Triage({ report: r, onRetry }) {
  const processing = r.status === "PROCESSING";
  return (
    <div className="sheet">
      {processing && (
        <Section title="Triage in progress">
          <p className="lead">
            Reading the failure description and checking this product's repair history. This page updates on its own.
          </p>
        </Section>
      )}
      {r.status === "FAILED" && (
        <Section title="Couldn't process" tone="failed">
          <p className="lead">Triage stopped before a report was produced. A specialist can run it again.</p>
          {r.error && <p className="muted mono-ish">{r.error}</p>}
          {onRetry && (
            <div className="row-actions">
              <button type="button" className="btn" onClick={onRetry}>
                Run triage again
              </button>
            </div>
          )}
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

      <Section title="Reported failure" note={r.customer_input.informative ? "From order" : "No usable detail"}>
        <p className="customer-text">{r.customer_input.text || "No description provided."}</p>
      </Section>

      {r.summary && (
        <Section title="Summary" note="AI generated">
          <p className="lead">{r.summary}</p>
        </Section>
      )}

      {r.predicted && (
        <Section title="Likely cause" note={r.review ? "Verified by specialist" : "AI prediction"}>
          <p className="cause-line">{r.predicted.causes.map((c) => CAUSE_LABELS[c] || c).join(", ") || "Not determined"}</p>
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
              From the synthetic reference manual provided for this hackathon. Not official Rockwell Automation
              documentation.
            </p>
          )}
        </Section>
      )}

      {r.bench_evidence?.length > 0 && <BenchEvidence items={r.bench_evidence} />}

      {r.unit_history && (
        <Section title="Unit history" note="From repair records">
          {r.unit_history.length === 0 ? (
            <p className="muted">No earlier repairs on record for this serial number.</p>
          ) : (
            <ul className="plain-list">
              {r.unit_history.map((h) => (
                <li key={h.order_id}>
                  {fmtDate(h.date)}: order {h.order_id}, {h.causes.map((c) => CAUSE_LABELS[c] || c).join(", ")}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {r.pending_sections?.length > 0 && !processing && (
        <Section title="Cleaning and testing" note="Pending">
          <p className="muted">Recorded by the technician after the repair.</p>
        </Section>
      )}
    </div>
  );
}

export default function ReportView({ report, onRetry }) {
  const [tab, setTab] = useState("triage");
  const processing = report.status === "PROCESSING";
  return (
    <div className="report-view">
      <ReportHeader report={report} />
      <div className="report-toolbar">
        <div className="tabs tabs-boxed" role="tablist" aria-label="Report view">
          {TABS.map(([v, label]) => (
            <button
              key={v}
              role="tab"
              id={`tab-${v}`}
              aria-selected={tab === v}
              aria-controls={`panel-${v}`}
              className={tab === v ? "on" : ""}
              onClick={() => setTab(v)}
            >
              {label}
            </button>
          ))}
        </div>
        <DownloadPdfButton orderId={report.order_id} disabled={processing} />
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="card report">
        {tab === "triage" ? <Triage report={report} onRetry={onRetry} /> : <RepairReport report={report} />}
      </div>
    </div>
  );
}

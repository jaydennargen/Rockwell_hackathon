import { fmtDate } from "../lib/format.js";
import StatusTag from "./StatusTag.jsx";

// Plain report header: order number, unit, status, and the order fields.
export default function ReportHeader({ report }) {
  const h = report.header;
  const fields = [
    ["Catalog", h.catalog],
    ["Serial", h.serial || "—"],
    ["Part number", h.part_number || "—"],
    ["Depot", h.depot || "—"],
    ["Received", fmtDate(h.received_date)],
    ["Line", h.item],
  ];
  return (
    <header className="card report-head">
      <div className="report-head-top">
        <div>
          <p className="kicker">Repair order</p>
          <h1 className="report-number">{h.order_number}</h1>
          <p className="report-desc">{h.description || "No description"}</p>
        </div>
        <span role="status">
          <StatusTag status={report.status} label={report.status_label} />
        </span>
      </div>
      <dl className="report-fields">
        {fields.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {report.status === "PROCESSING" && <span className="progress" aria-hidden="true" />}
    </header>
  );
}

import { fmtDate } from "../lib/format.js";
import { STATUS_TONE } from "../lib/format.js";

// The report header, drawn as the paper tag that travels with a unit through the depot.
export default function RepairTag({ report }) {
  const h = report.header;
  const tone = STATUS_TONE[report.status] || "processing";
  const fields = [
    ["Catalog", h.catalog],
    ["Part number", h.part_number || "—"],
    ["Serial", h.serial || "—"],
    ["Depot", h.depot || "—"],
    ["Received", fmtDate(h.received_date)],
    ["Item", h.item],
  ];
  return (
    <section className="repair-tag" aria-label="Repair order">
      <span className="repair-tag-hole" aria-hidden="true" />
      <div className="repair-tag-body">
        <p className="repair-tag-kicker">Repair order</p>
        <h1 className="repair-tag-number">{h.order_number}</h1>
        <p className="repair-tag-desc">{h.description || "No description"}</p>
        <dl className="repair-tag-fields">
          {fields.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className={`stamp tone-${tone}`} key={report.status} role="status">
        {report.status_label}
      </div>
      {report.status === "PROCESSING" && <span className="repair-tag-progress" aria-hidden="true" />}
    </section>
  );
}

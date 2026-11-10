import { BRAND } from "../lib/brand.js";
import { AREA_LABELS, CAUSE_SAP, fmtSapDate } from "../lib/format.js";

// The report in the layout of the SAP "Remanufacturing/Repair Report" (reference PDF).
// Mirrors report_sections() in backend/app/report_pdf.py, so the page and the PDF download match.
// This is a pre-repair document: post-repair sections are always PENDING, never filled in.

const NA = "Not provided";
const PENDING = "Pending: to be completed by the technician after repair.";
const TAGS = {
  FROM_ORDER: ["From order", "src"],
  PREDICTION: ["AI prediction, not verified", "ai"],
  VERIFIED: ["Verified by specialist", "ok"],
  PENDING: ["Pending, technician", "pending"],
};
const SAP_FIELDS = /\s+(?=(?:Serial Number|Ship\/End Customer PO|PO#|RAAMP BARCODE|CAT#)\s*[:=])/i;

const commentLines = (raw) =>
  (raw || "").split("\n").flatMap((ln) => ln.trim().split(SAP_FIELDS)).filter(Boolean);

function sections(r) {
  const name = BRAND.name;
  const ci = r.customer_input || {};
  const pred = r.predicted;
  const review = r.review || {};
  const verified = ["APPROVED", "EDITED"].includes(r.status) && r.review
    ? `Confirmed by specialist review (${review.reviewer}, ${fmtSapDate(review.reviewed_at)}).`
    : null;

  const distributor = ["Comments:", ...(commentLines(ci.raw || ci.text).length ? commentLines(ci.raw || ci.text) : ["None provided."])];
  if (ci.additional_info) distributor.push("", "Additional Information:", ...commentLines(ci.additional_info));

  const unreleased = (what) =>
    r.status === "PROCESSING" ? [`${name} is still triaging this order.`]
    : r.status === "FAILED" ? [`${name} couldn't process this order, so no ${what} is available.`]
    : r.status === "REJECTED" ? ["Not released. See the specialist notes below."]
    : [`Pending specialist review. A repair specialist is checking this order before any ${what} is released.`];

  let tag = verified ? "VERIFIED" : "PREDICTION";
  let affected, causes;
  if (pred) {
    const areas = [...new Set(pred.areas.map((a) =>
      a.detail && a.detail !== "From product history" ? a.detail : AREA_LABELS[a.category] || a.category))];
    affected = [
      ...(verified ? [verified] : [`Predicted by ${name} from the distributor input and this product's repair history. Not yet confirmed by inspection or testing. The following areas are likely affected:`]),
      ...(areas.length ? areas.map((a) => `* ${a}`) : ["* None identified"]),
    ];
    causes = [
      ...(verified ? [verified] : [`${name} offers this estimate of probable cause based on information accompanying the returned unit and this product's repair history:`]),
      ...(pred.causes.length ? pred.causes.map((c) => `* ${CAUSE_SAP[c] || c}`) : ["* Not determined"]),
    ];
  } else {
    tag = "PENDING";
    affected = unreleased("prediction");
    causes = unreleased("probable cause");
  }

  const out = [
    ["Distributor Input", "FROM_ORDER", distributor],
    ["As Received", "PENDING", [PENDING]],
    ["Cleaning", "PENDING", [PENDING]],
    ["Updates", "PENDING", [PENDING]],
    ["Affected Areas", tag, affected],
    ["Parts Replaced", "PENDING", [PENDING]],
    ["Testing", "PENDING", [PENDING]],
    ["Probable Cause Code", tag, causes],
  ];
  if (review.notes)
    out.push(["Specialist Notes", "VERIFIED", [`${review.reviewer}, ${fmtSapDate(review.reviewed_at)}:`, review.notes]]);
  return out;
}

export default function RepairReport({ report }) {
  const h = report.header;
  const row1 = [
    ["Part Number", h.catalog],
    ["Serial Number", h.serial],
    ["Description", h.description],
    ["Repair Order No", h.order_number],
    ["Repair Item", h.item],
  ];
  const row2 = [
    ["Purchase Order No", h.purchase_order || NA],
    ["Date Received", fmtSapDate(h.received_date)],
    ["Date Shipped", "Not shipped"],
    ["Date of Manufacture", ""],
  ];
  return (
    <article className="sap" aria-label="Remanufacturing/Repair Report">
      <header className="sap-band">
        <span className="sap-brand">{BRAND.name}</span>
        <h2 className="sap-title">Remanufacturing/Repair Report</h2>
        <p className="sap-date">{fmtSapDate(new Date())}</p>
      </header>

      <div className="sap-parties">
        <p>
          Sold To Party: {NA}
          <br />Name: {h.sold_to || NA}
          <br />Address: {NA}
        </p>
        <p>
          End Customer: {NA}
          <br />Name: {NA}
          <br />Address: {NA}
        </p>
      </div>
      <div className="sap-gap" />

      <div className="sap-table-wrap">
        <table className="sap-table sap-table-5">
          <thead>
            <tr>{row1.map(([k]) => <th key={k} scope="col">{k}</th>)}</tr>
          </thead>
          <tbody>
            <tr>{row1.map(([k, v]) => <td key={k}>{v}</td>)}</tr>
          </tbody>
        </table>
        <table className="sap-table sap-table-4">
          <thead>
            <tr>{row2.map(([k]) => <th key={k} scope="col">{k}</th>)}</tr>
          </thead>
          <tbody>
            <tr>{row2.map(([k, v]) => <td key={k}>{v}</td>)}</tr>
          </tbody>
        </table>
      </div>

      {sections(report).map(([title, tag, lines]) => (
        <section key={title} className="sap-sec">
          <h3 className="sap-bar">
            <span>{title}</span>
            <span className={`sap-tag sap-tag-${TAGS[tag][1]}`}>{TAGS[tag][0]}</span>
          </h3>
          <div className={`sap-body${tag === "PENDING" ? " is-pending" : ""}`}>
            {lines.map((ln, i) => (ln ? <p key={i}>{ln}</p> : <br key={i} />))}
          </div>
        </section>
      ))}

      <p className="sap-foot">
        Pre-repair triage draft generated by {BRAND.name}. AI predictions are not inspection results. Not an
        official Rockwell Automation document.
      </p>
    </article>
  );
}

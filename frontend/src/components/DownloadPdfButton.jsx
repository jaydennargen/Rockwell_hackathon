import { useState } from "react";
import * as api from "../api/client.js";

// Downloads the repair report PDF (reference SAP layout). Shows loading, error, and done states.
export default function DownloadPdfButton({ orderId, disabled }) {
  const [state, setState] = useState("idle"); // idle | busy | done | error
  const [error, setError] = useState(null);

  async function download() {
    setState("busy");
    setError(null);
    try {
      const blob = await api.downloadReportPdf(orderId);
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), { href: url, download: `repair-report-${orderId}.pdf` });
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setState("done");
    } catch (e) {
      setError(e.message);
      setState("error");
    }
  }

  return (
    <div className="pdf-action">
      <button type="button" className="btn btn-secondary" onClick={download} disabled={disabled || state === "busy"}>
        {state === "busy" ? "Preparing PDF" : "Download PDF report"}
      </button>
      <span className="pdf-status" role="status">
        {state === "done" && "Downloaded."}
        {state === "error" && <span className="txt-failed">{error}</span>}
      </span>
    </div>
  );
}

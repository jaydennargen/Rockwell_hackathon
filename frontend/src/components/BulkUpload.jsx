import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/client.js";

export default function BulkUpload() {
  const input = useRef(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function upload(file) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.bulkUpload(file));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bulk">
      <div
        className={`dropzone${drag ? " is-drag" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          upload(e.dataTransfer.files[0]);
        }}
      >
        <p>
          <strong>Upload an SAP export</strong> to submit many orders at once. Use the same columns as the
          repair order extract (.xlsx or .csv).
        </p>
        <button type="button" className="btn-quiet" disabled={busy} onClick={() => input.current.click()}>
          {busy ? "Uploading" : "Choose file"}
        </button>
        <input
          ref={input}
          type="file"
          accept=".xlsx,.csv"
          hidden
          onChange={(e) => upload(e.target.files[0])}
        />
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {result && (
        <div className="bulk-result" role="status">
          <p>
            Submitted {result.order_ids.length} order{result.order_ids.length === 1 ? "" : "s"}.{" "}
            <Link to="/requests">See them in your requests</Link>
          </p>
          {result.errors.length > 0 && (
            <ul className="plain-list">
              {result.errors.slice(0, 8).map((er) => (
                <li key={er.row}>
                  Row {er.row}: {er.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import * as api from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import StatusTag from "../components/StatusTag.jsx";
import { fmtDateTime, pct } from "../lib/format.js";

const FILTERS = [
  ["needs_review", "Needs review"],
  ["released", "Released"],
  ["all", "All"],
];

export default function RequestListPage() {
  const { role } = useAuth();
  const specialist = role === "specialist";
  const [params, setParams] = useSearchParams();
  const filter = specialist ? params.get("filter") || "needs_review" : "all";
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const nav = useNavigate();

  const load = useCallback(
    () => api.listOrders({ filter }).then(setData).catch((e) => setError(e.message)),
    [filter]
  );

  useEffect(() => {
    setData(null);
    load();
  }, [load]);

  // keep the list fresh while anything is still processing
  useEffect(() => {
    if (!data?.items.some((o) => o.status === "PROCESSING")) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [data, load]);

  return (
    <div className="list-page">
      <div className="page-head">
        <h1>{specialist ? "Repair requests" : "Your repair requests"}</h1>
        <Link to="/requests/new" className="btn">
          New request
        </Link>
      </div>

      {specialist && (
        <div className="tabs" role="tablist" aria-label="Filter requests">
          {FILTERS.map(([v, label]) => (
            <button
              key={v}
              role="tab"
              aria-selected={filter === v}
              className={filter === v ? "on" : ""}
              onClick={() => setParams({ filter: v })}
            >
              {label}
              {filter === v && data ? <span className="tab-count">{data.total}</span> : null}
            </button>
          ))}
        </div>
      )}

      {error && <p className="form-error" role="alert">{error}</p>}
      {!data && !error && <p className="muted pad">Loading requests</p>}

      {data && data.items.length === 0 && (
        <div className="empty">
          {specialist && filter === "needs_review" ? (
            <p>Nothing is waiting for review.</p>
          ) : (
            <>
              <p>No repair requests yet.</p>
              <Link to="/requests/new" className="btn">
                Submit your first request
              </Link>
            </>
          )}
        </div>
      )}

      {data && data.items.length > 0 && (
        <table className="ledger ledger-orders">
          <thead>
            <tr>
              <th scope="col">Order</th>
              <th scope="col">Unit</th>
              <th scope="col" className="hide-sm">Serial</th>
              {specialist && <th scope="col" className="hide-sm">Why it's flagged</th>}
              {specialist && <th scope="col" className="num hide-sm">Confidence</th>}
              <th scope="col" className="hide-sm">Submitted</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((o) => (
              <tr key={o.order_id} onClick={() => nav(`/requests/${o.order_id}`)}>
                <td className="order-no">
                  <Link to={`/requests/${o.order_id}`} onClick={(e) => e.stopPropagation()}>
                    {o.order_id}
                  </Link>
                </td>
                <td>
                  <span className="unit-desc">{o.part_description || "—"}</span>
                  <span className="unit-cat">{o.catalog}</span>
                </td>
                <td className="hide-sm">{o.serial_number || "—"}</td>
                {specialist && <td className="hide-sm reason">{o.top_reason || "—"}</td>}
                {specialist && (
                  <td className="num hide-sm">{o.confidence_score != null ? pct(o.confidence_score) : "—"}</td>
                )}
                <td className="hide-sm">{fmtDateTime(o.created_at)}</td>
                <td>
                  <StatusTag status={o.status} label={o.status_label} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

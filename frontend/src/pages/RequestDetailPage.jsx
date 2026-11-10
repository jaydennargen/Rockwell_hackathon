import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ChatPanel from "../components/ChatPanel.jsx";
import ReportView from "../components/ReportView.jsx";
import ReviewPanel from "../components/ReviewPanel.jsx";

export default function RequestDetailPage() {
  const { id } = useParams();
  const { role } = useAuth();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(
    () =>
      api
        .getOrder(id)
        .then((r) => {
          setReport(r);
          setError(null);
        })
        .catch((e) => setError(e)),
    [id]
  );

  useEffect(() => {
    setReport(null);
    load();
  }, [load]);

  useEffect(() => {
    if (report?.status !== "PROCESSING") return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [report?.status, load]);

  const back = (
    <Link to="/requests" className="back">
      {role === "specialist" ? "All requests" : "My requests"}
    </Link>
  );

  if (error)
    return (
      <div className="detail-page">
        {back}
        <div className="empty">
          <p>
            {error.status === 404
              ? "This request doesn't exist or isn't shared with your account."
              : error.message}
          </p>
        </div>
      </div>
    );

  if (!report)
    return (
      <div className="detail-page">
        {back}
        <p className="muted pad">Loading the report</p>
      </div>
    );

  return (
    <div className="detail-page">
      {back}
      <div className="detail-grid">
        <ReportView
          report={report}
          onRetry={
            role === "specialist"
              ? () => api.retryOrder(id).then(load).catch((e) => setError(e))
              : undefined
          }
        />
        <aside className="detail-side">
          {role === "specialist" && <ReviewPanel key={report.updated_at} report={report} onReviewed={setReport} />}
          <ChatPanel key={`${report.order_id}-${report.status}`} report={report} role={role} />
        </aside>
      </div>
    </div>
  );
}

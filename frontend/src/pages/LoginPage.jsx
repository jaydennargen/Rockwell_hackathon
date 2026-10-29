import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import Wordmark from "../components/Wordmark.jsx";

const ROLES = [
  {
    role: "requester",
    title: "Field technician",
    body: "Submit a repair order and get the likely cause and troubleshooting steps.",
    who: "Dana Whitfield, Van Meter Inc",
  },
  {
    role: "specialist",
    title: "Repair specialist",
    body: "Review escalated tickets: AI confidence per category and why.",
    who: "Luis Ortega, repair specialist",
  },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  if (user) return <Navigate to="/" replace />;

  async function pick(role) {
    setBusy(role);
    setError(null);
    try {
      await login(role);
      nav(loc.state?.from || "/", { replace: true });
    } catch (e) {
      setError(e.message);
      setBusy(null);
    }
  }

  return (
    <main className="login">
      <div className="login-inner">
        <Wordmark />
        <h1 className="login-title">Failure triage for repair orders</h1>
        <p className="login-sub">
          Orders the AI isn't confident about go to a specialist before anything is released.
        </p>
        <div className="login-roles">
          {ROLES.map((r) => (
            <button key={r.role} className="role-choice" onClick={() => pick(r.role)} disabled={!!busy}>
              <span className="role-title">{r.title}</span>
              <span className="role-body">{r.body}</span>
              <span className="role-who">{busy === r.role ? "Signing in" : `Sign in as ${r.who}`}</span>
            </button>
          ))}
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <p className="fineprint">Demo sign-in for the SHPE AI Hackathon. No password needed.</p>
      </div>
    </main>
  );
}

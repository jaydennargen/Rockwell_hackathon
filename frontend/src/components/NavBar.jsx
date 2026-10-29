import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import Wordmark from "./Wordmark.jsx";

export default function NavBar() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const isSpecialist = user.role === "specialist";
  return (
    <header className="topbar">
      <Link to="/" className="topbar-brand" aria-label="Triage Desk home">
        <Wordmark />
      </Link>
      <nav className="topbar-nav" aria-label="Main">
        <NavLink to="/requests" end>
          {isSpecialist ? "All requests" : "My requests"}
        </NavLink>
        <NavLink to="/requests/new">New request</NavLink>
      </nav>
      <div className="topbar-user">
        <span className="topbar-name">{user.name}</span>
        <span className="topbar-org">
          {isSpecialist ? "Repair specialist" : user.org}
        </span>
        <button
          className="btn-quiet"
          onClick={async () => {
            await logout();
            nav("/login");
          }}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

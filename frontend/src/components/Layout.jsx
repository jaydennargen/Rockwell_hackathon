import { Outlet } from "react-router-dom";
import NavBar from "./NavBar.jsx";

export default function Layout() {
  return (
    <div className="shell">
      <NavBar />
      <main className="page" id="main">
        <Outlet />
      </main>
    </div>
  );
}

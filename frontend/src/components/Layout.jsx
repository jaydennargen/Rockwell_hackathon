import { Outlet } from "react-router-dom";
import { BRAND } from "../lib/brand.js";
import NavBar from "./NavBar.jsx";

export default function Layout() {
  return (
    <div className="shell">
      <NavBar />
      <main className="page" id="main">
        <Outlet />
      </main>
      <footer className="site-foot">
        <span>
          {BRAND.name}: {BRAND.long}
        </span>
        <span>Rockwell Automation × SHPE 2026 Hackathon · Powered by Databricks</span>
      </footer>
    </div>
  );
}

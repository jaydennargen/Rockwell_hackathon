import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext.jsx";
import RequireRole from "./auth/RequireRole.jsx";
import Layout from "./components/Layout.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import NewRequestPage from "./pages/NewRequestPage.jsx";
import RequestDetailPage from "./pages/RequestDetailPage.jsx";
import RequestListPage from "./pages/RequestListPage.jsx";

function Home() {
  const { role } = useAuth();
  return <Navigate to={role === "specialist" ? "/requests?filter=needs_review" : "/requests"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireRole>
            <Layout />
          </RequireRole>
        }
      >
        <Route path="/" element={<Home />} />
        <Route path="/requests" element={<RequestListPage />} />
        <Route path="/requests/new" element={<NewRequestPage />} />
        <Route path="/requests/:id" element={<RequestDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

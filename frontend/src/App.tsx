import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import LoginPage from "./pages/LoginPage";
import InboxPage from "./pages/InboxPage";

function RequireAuth({ children }: { children: JSX.Element }) {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });
  if (me.isPending) return <div className="p-8 text-sm text-ink-soft">Loading…</div>;
  if (me.isError) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const qc = useQueryClient();
  const navigate = useNavigate();

  // Any 401 (expired session) sends the user back to the login page and drops cached data
  useEffect(() => {
    const onExpired = () => { qc.clear(); navigate("/login", { replace: true }); };
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, [qc, navigate]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={<RequireAuth><InboxPage /></RequireAuth>} />
    </Routes>
  );
}

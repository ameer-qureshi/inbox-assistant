import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await api.login(email, password);
      qc.setQueryData(["me"], user);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401
        ? "Email or password is incorrect."
        : "The server cannot be reached. Check that the backend is running.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-line bg-sheet p-7 shadow-[0_1px_0_#D5DBE3]">
        <div className="mb-6 flex items-center gap-3">
          <span aria-hidden className="flex h-9 w-9 flex-col justify-center gap-1 rounded-md bg-ink px-2">
            <span className="h-1 rounded-full bg-p1" />
            <span className="h-1 w-4/5 rounded-full bg-p2" />
            <span className="h-1 w-3/5 rounded-full bg-p3" />
          </span>
          <div>
            <h1 className="text-lg font-bold leading-tight">Inbox Assistant</h1>
            <p className="text-sm text-ink-soft">Sign in to see your mail</p>
          </div>
        </div>
        <label className="mb-1 block text-sm font-medium" htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" required className="field mb-4"
               value={email} onChange={(e) => setEmail(e.target.value)} />
        <label className="mb-1 block text-sm font-medium" htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete="current-password" required className="field mb-5"
               value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p role="alert" className="mb-4 rounded-md bg-p1-tint px-3 py-2 text-sm text-p1">{error}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </main>
  );
}

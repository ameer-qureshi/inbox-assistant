import { useMemo } from "react";
import { Link, Route, Routes, useLocation, useMatch, useNavigate, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Filters } from "../api";
import TodayPanel from "../components/TodayPanel";
import FilterBar from "../components/FilterBar";
import EmailRow from "../components/EmailRow";
import ThreadView from "../components/ThreadView";

const FILTER_KEYS = ["category", "priority", "status", "sender", "date_from", "date_to", "q", "page"] as const;

export default function InboxPage() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const threadMatch = useMatch("/thread/:threadId");
  const openThreadId = threadMatch ? Number(threadMatch.params.threadId) : null;

  // Filters live in the URL: shareable, survive refresh, and the back button works
  const filters: Filters = useMemo(() => {
    const f: Filters = {};
    FILTER_KEYS.forEach((k) => { const v = params.get(k); if (v) f[k] = v; });
    return f;
  }, [params]);

  const setFilters = (next: Filters) => {
    const p = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => { if (v) p.set(k, v); });
    setParams(p);
  };

  const list = useQuery({
    queryKey: ["emails", filters],
    queryFn: () => api.emails(filters),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000, // new mail from the 10-minute sync shows up without reload
  });

  const page = Number(filters.page ?? 1);
  const goPage = (p: number) => setFilters({ ...filters, page: String(p) });
  const search = location.search;

  async function signOut() {
    await api.logout().catch(() => undefined);
    qc.clear();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center gap-3 border-b border-line bg-sheet px-4 py-2.5">
        <Link to={{ pathname: "/", search }} className="flex items-center gap-2.5" aria-label="Inbox home">
          <span aria-hidden className="flex h-7 w-7 flex-col justify-center gap-[3px] rounded bg-ink px-1.5">
            <span className="h-[3px] rounded-full bg-p1" />
            <span className="h-[3px] w-4/5 rounded-full bg-p2" />
            <span className="h-[3px] w-3/5 rounded-full bg-p3" />
          </span>
          <span className="hidden font-bold sm:inline">Inbox Assistant</span>
        </Link>
        <form className="ml-auto w-full max-w-md" role="search"
              onSubmit={(e) => {
                e.preventDefault();
                const q = new FormData(e.currentTarget).get("q") as string;
                setFilters({ ...filters, q: q.trim() || undefined, page: undefined });
              }}>
          <label htmlFor="q" className="sr-only">Search subject and content</label>
          <input id="q" name="q" key={filters.q ?? ""} defaultValue={filters.q ?? ""}
                 placeholder="Search subject and content" className="field py-1.5" />
        </form>
        <button onClick={signOut} className="btn-quiet shrink-0 py-1.5">Sign out</button>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(380px,470px)_1fr]">
        {/* Left column: hidden on mobile when a thread is open */}
        <section className={`min-h-0 overflow-y-auto border-line lg:border-r ${openThreadId ? "hidden lg:block" : ""}`}
                 aria-label="Email list">
          <TodayPanel search={search} />
          <FilterBar filters={filters} onChange={setFilters} />

          <div className="flex items-baseline justify-between px-4 pb-2 pt-3 text-sm">
            <h2 className="font-semibold">All mail</h2>
            {list.data && <span className="text-ink-soft">{list.data.total} email{list.data.total === 1 ? "" : "s"}</span>}
          </div>

          {list.isError && (
            <p role="alert" className="mx-4 rounded-md bg-p1-tint px-3 py-2 text-sm text-p1">
              The list could not be loaded. <button className="underline" onClick={() => list.refetch()}>Try again</button>
            </p>
          )}
          {list.data && list.data.items.length === 0 && (
            <div className="mx-4 rounded-md border border-dashed border-line px-4 py-8 text-center text-sm text-ink-soft">
              No email matches these filters.{" "}
              <button className="font-semibold text-post underline" onClick={() => setFilters({})}>Clear filters</button>
            </div>
          )}

          <ul className={`divide-y divide-line border-y border-line bg-sheet ${list.isPlaceholderData ? "opacity-60" : ""}`}>
            {list.data?.items.map((e) => (
              <li key={e.id}>
                <EmailRow email={e} active={e.thread_id === openThreadId}
                          to={{ pathname: `/thread/${e.thread_id}`, search }} />
              </li>
            ))}
          </ul>

          {list.data && list.data.pages > 1 && (
            <nav className="flex items-center justify-between px-4 py-4 text-sm" aria-label="Pagination">
              <button className="btn-quiet" disabled={page <= 1} onClick={() => goPage(page - 1)}>Previous</button>
              <span className="text-ink-soft">Page {page} of {list.data.pages}</span>
              <button className="btn-quiet" disabled={page >= list.data.pages} onClick={() => goPage(page + 1)}>Next</button>
            </nav>
          )}
        </section>

        <section className={`min-h-0 overflow-y-auto ${openThreadId ? "" : "hidden lg:block"}`} aria-label="Conversation">
          <Routes>
            <Route path="/thread/:threadId" element={openThreadId ? <ThreadView key={openThreadId} threadId={openThreadId} backTo={{ pathname: "/", search }} /> : null} />
            <Route path="*" element={
              <div className="flex h-full items-center justify-center p-8 text-center text-sm text-ink-soft">
                Pick an email to read the conversation and reply.
              </div>} />
          </Routes>
        </section>
      </div>
    </div>
  );
}

import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { PRIORITY_STYLE } from "../format";

export default function TodayPanel({ search }: { search: string }) {
  // Open by default on desktop, collapsed on phones so the list stays visible
  const [open, setOpen] = useState(() => window.matchMedia("(min-width: 1024px)").matches);
  const q = useQuery({ queryKey: ["summary"], queryFn: api.summary, refetchInterval: 120_000 });

  return (
    <section aria-labelledby="today-title" className="border-b border-line bg-ink text-white">
      <button onClick={() => setOpen(!open)} aria-expanded={open}
              className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <h2 id="today-title" className="font-bold">Today</h2>
        {q.data && (
          <span className="text-sm text-white/70">
            {q.data.total} received, {q.data.to_process} to handle, {q.data.high_priority} urgent
          </span>
        )}
        <span aria-hidden className={`ml-auto text-white/60 transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
      </button>

      {open && (
        <div className="px-4 pb-4">
          {q.isPending && <p className="text-sm text-white/70">Preparing the summary…</p>}
          {q.isError && <p className="text-sm text-white/80">The summary is not available right now.</p>}
          {q.data && (
            <>
              <p className="mb-3 max-w-prose text-sm leading-relaxed text-white/85">{q.data.summary}</p>
              {q.data.top.length === 0 ? (
                <p className="text-sm text-white/70">Nothing waiting. Enjoy the quiet.</p>
              ) : (
                <>
                  <h3 className="mb-1.5 text-sm font-semibold text-white/90">Handle these first</h3>
                  <ol className="space-y-1.5">
                    {q.data.top.map(({ email, reason }, i) => {
                      const tint = email.priority ? PRIORITY_STYLE[email.priority].bar : "bg-white/30";
                      // reason is "a · b · c" from the API: shown as separate chips
                      const [lead, ...rest] = reason.split(" · ");
                      return (
                        <li key={email.id}>
                          <Link to={{ pathname: `/thread/${email.thread_id}`, search }}
                                className="flex gap-3 rounded-md bg-white/[0.06] p-2.5 hover:bg-white/[0.12]">
                            <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded text-xs font-bold text-white ${tint}`}>
                              {i + 1}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-semibold">{email.subject}</span>
                              <span className="block truncate text-xs text-white/70">{email.from_name || email.from_address}</span>
                              <span className="mt-1 flex flex-wrap gap-1">
                                <span className="rounded bg-white/15 px-1.5 py-px text-[11px] font-semibold">{lead}</span>
                                {rest.map((r) => (
                                  <span key={r} className="rounded bg-white/[0.08] px-1.5 py-px text-[11px] text-white/80">{r}</span>
                                ))}
                              </span>
                            </span>
                          </Link>
                        </li>
                      );
                    })}
                  </ol>
                </>
              )}
              {!q.data.ai_generated && q.data.total > 0 && (
                <p className="mt-2 text-xs text-white/50">Summary computed without AI.</p>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

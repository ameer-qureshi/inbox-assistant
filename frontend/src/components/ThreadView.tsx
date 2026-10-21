import { Link, To } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, EmailOut, Reply } from "../api";
import { longDate } from "../format";
import { CategoryBadge, PriorityBadge, ReviewFlag, StatusText } from "./Badges";
import ReplyComposer from "./ReplyComposer";
import ReplyStatusLine from "./ReplyStatusLine";

type Item = { kind: "email"; at: string; email: EmailOut } | { kind: "reply"; at: string; reply: Reply };

export default function ThreadView({ threadId, backTo }: { threadId: number; backTo: To }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["thread", threadId],
    queryFn: () => api.thread(threadId),
    // While a reply is being sent, poll so the status updates by itself
    refetchInterval: (query) => query.state.data?.replies.some((r) => r.status === "sending") ? 1500 : false,
  });

  const toggleIgnore = useMutation({
    mutationFn: (e: EmailOut) => api.setStatus(e.id, e.status === "ignored" ? "to_process" : "ignored"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["thread", threadId] });
      qc.invalidateQueries({ queryKey: ["emails"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
    },
  });

  if (q.isPending) return <p className="p-6 text-sm text-ink-soft">Loading the conversation…</p>;
  if (q.isError) return <p role="alert" className="p-6 text-sm text-p1">This conversation could not be loaded.</p>;

  const t = q.data;
  const inbound = t.messages.filter((m) => !m.is_outbound);
  const target = inbound[inbound.length - 1]; // we reply to the latest received message
  const items: Item[] = [
    ...t.messages.map((email) => ({ kind: "email" as const, at: email.received_at, email })),
    ...t.replies.map((reply) => ({ kind: "reply" as const, at: reply.created_at, reply })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  return (
    <article className="mx-auto max-w-3xl px-4 py-4 lg:px-8 lg:py-6">
      <Link to={backTo} className="mb-3 inline-block text-sm font-semibold text-post lg:hidden">Back to inbox</Link>

      <header className="mb-5">
        <h1 className="text-xl font-bold leading-snug lg:text-2xl">{t.subject || "(no subject)"}</h1>
        {target && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <PriorityBadge priority={target.priority} />
            <CategoryBadge category={target.category} />
            {target.needs_review && <ReviewFlag />}
            <StatusText status={target.status} />
            {target.status !== "replied" && (
              <button className="ml-auto text-sm text-ink-soft underline" disabled={toggleIgnore.isPending}
                      onClick={() => toggleIgnore.mutate(target)}>
                {target.status === "ignored" ? "Move back to To process" : "Ignore"}
              </button>
            )}
          </div>
        )}
        {target?.expected_action && (
          <p className="mt-3 rounded-md border-l-4 border-post bg-post-tint px-3 py-2 text-sm">
            <span className="font-semibold">Suggested next step: </span>{target.expected_action}
          </p>
        )}
      </header>

      <ol className="space-y-3">
        {items.map((it) => it.kind === "email" ? (
          <li key={`e${it.email.id}`}
              className={`rounded-lg border border-line p-4 ${it.email.is_outbound ? "ml-6 bg-post-tint/50" : "bg-sheet"}`}>
            <div className="mb-2 flex flex-wrap items-baseline gap-x-2 text-sm">
              <span className="font-semibold">{it.email.is_outbound ? "You" : it.email.from_name || it.email.from_address}</span>
              {!it.email.is_outbound && <span className="text-ink-soft">{it.email.from_address}</span>}
              <time className="ml-auto text-xs text-ink-soft" dateTime={it.email.received_at}>{longDate(it.email.received_at)}</time>
            </div>
            <div className="whitespace-pre-wrap break-words font-read text-[15px] leading-7">{it.email.body_text}</div>
          </li>
        ) : (
          <li key={`r${it.reply.id}`} className="ml-6 rounded-lg border border-line bg-post-tint/50 p-4">
            <div className="mb-2 flex items-baseline gap-2 text-sm">
              <span className="font-semibold">You</span>
              <time className="ml-auto text-xs text-ink-soft" dateTime={it.reply.created_at}>{longDate(it.reply.created_at)}</time>
            </div>
            <div className="whitespace-pre-wrap break-words font-read text-[15px] leading-7">{it.reply.body}</div>
            <ReplyStatusLine reply={it.reply} threadId={threadId} />
          </li>
        ))}
      </ol>

      {target && !t.replies.some((r) => r.status !== "sent") && (
        <ReplyComposer key={target.id} email={target} threadId={threadId} latestDraft={t.latest_draft} />
      )}
    </article>
  );
}

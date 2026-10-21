import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Reply } from "../api";

export default function ReplyStatusLine({ reply, threadId }: { reply: Reply; threadId: number }) {
  const qc = useQueryClient();
  const retry = useMutation({
    mutationFn: () => api.retry(reply.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["thread", threadId] }),
  });

  if (reply.status === "sending") {
    return (
      <p className="mt-3 flex items-center gap-2 text-sm text-ink-soft" role="status">
        <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-post" />
        Sending{reply.attempts > 1 ? ` (attempt ${reply.attempts})` : ""}…
      </p>
    );
  }
  if (reply.status === "sent") {
    return <p className="mt-3 text-sm font-medium text-ok" role="status">Sent</p>;
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md bg-p1-tint px-3 py-2 text-sm text-p1" role="alert">
      <span><span className="font-semibold">Not sent.</span> {reply.error ?? "The email could not be delivered."}</span>
      <button className="btn-quiet ml-auto py-1" disabled={retry.isPending} onClick={() => retry.mutate()}>
        {retry.isPending ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}

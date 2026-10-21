import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, Draft, EmailOut, newIdempotencyKey, Tone } from "../api";

const TONES: { value: Tone; label: string }[] = [
  { value: "formal", label: "Formal" },
  { value: "neutral", label: "Neutral" },
  { value: "short", label: "Short" },
];

interface Props { email: EmailOut; threadId: number; latestDraft: Draft | null }

export default function ReplyComposer({ email, threadId, latestDraft }: Props) {
  const qc = useQueryClient();
  const usableDraft = latestDraft && latestDraft.email_id === email.id && email.status === "draft_ready" ? latestDraft : null;
  const [open, setOpen] = useState(email.status !== "replied");
  const [text, setText] = useState(usableDraft?.body ?? "");
  const [draftId, setDraftId] = useState<number | undefined>(usableDraft?.id);
  const [aiText, setAiText] = useState(usableDraft?.body ?? "");
  const [tone, setTone] = useState<Tone>(usableDraft?.tone ?? "neutral");
  const [confirming, setConfirming] = useState(false);
  // One key per user validation: a double click or a network retry reuses it,
  // so the backend creates (and sends) the reply only once.
  const keyRef = useRef<string | null>(null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["thread", threadId] });
    qc.invalidateQueries({ queryKey: ["emails"] });
    qc.invalidateQueries({ queryKey: ["summary"] });
  };

  const draft = useMutation({
    mutationFn: (t: Tone) => api.draft(email.id, t),
    onSuccess: (d) => { setText(d.body); setAiText(d.body); setDraftId(d.id); refresh(); },
  });

  const send = useMutation({
    mutationFn: () => api.reply(email.id, text.trim(), keyRef.current!, draftId),
    onSuccess: () => {
      keyRef.current = null;
      setConfirming(false);
      setText("");
      setOpen(false);
      refresh();
    },
  });

  function askAI() {
    const edited = text.trim() && text !== aiText;
    if (edited && !window.confirm("Replace your current text with a new AI draft?")) return;
    draft.mutate(tone);
  }

  function review() {
    keyRef.current = newIdempotencyKey();
    setConfirming(true);
  }

  if (!open) {
    return (
      <div className="mt-5">
        <button className="btn-quiet" onClick={() => setOpen(true)}>Write another reply</button>
      </div>
    );
  }

  const busy = draft.isPending || send.isPending;

  return (
    <section className="mt-5 rounded-lg border border-line bg-sheet p-4" aria-label="Reply">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-sm font-semibold">Reply to {email.from_name || email.from_address}</h2>
        <div role="radiogroup" aria-label="Tone of the AI draft" className="flex rounded-md border border-line p-0.5">
          {TONES.map((t) => (
            <button key={t.value} role="radio" aria-checked={tone === t.value} disabled={busy || confirming}
                    onClick={() => setTone(t.value)}
                    className={`rounded px-2.5 py-1 text-xs font-semibold ${tone === t.value ? "bg-ink text-white" : "text-ink-soft hover:text-ink"}`}>
              {t.label}
            </button>
          ))}
        </div>
        <button className="btn-quiet py-1.5" onClick={askAI} disabled={busy || confirming}>
          {draft.isPending ? "Writing…" : aiText ? "New AI draft" : "Write with AI"}
        </button>
      </div>

      <label htmlFor="reply-body" className="sr-only">Reply text</label>
      <textarea id="reply-body" rows={8} className="field font-read text-[15px] leading-7"
                placeholder="Write your reply, or let the AI draft it and edit it here."
                value={text} disabled={confirming} onChange={(e) => setText(e.target.value)} />

      {draft.isError && (
        <p role="alert" className="mt-2 text-sm text-p1">
          The AI draft failed: {(draft.error as ApiError).message}. You can write the reply yourself.
        </p>
      )}
      {aiText && text === aiText && (
        <p className="mt-2 text-xs text-ink-soft">AI draft. Read and edit it before sending; it will not be sent without your confirmation.</p>
      )}

      {!confirming ? (
        <div className="mt-3 flex justify-end">
          <button className="btn-primary" disabled={!text.trim() || busy} onClick={review}>Review and send</button>
        </div>
      ) : (
        <div className="mt-3 rounded-md border border-post bg-post-tint p-3" role="dialog" aria-label="Confirm sending">
          <p className="text-sm">
            Send this reply to <span className="font-semibold">{email.from_address}</span> in the same conversation?
          </p>
          {send.isError && (
            <p role="alert" className="mt-2 text-sm text-p1">
              Not sent: {(send.error as ApiError).message}. Pressing Send again is safe, it will not send twice.
            </p>
          )}
          <div className="mt-3 flex justify-end gap-2">
            <button className="btn-quiet" disabled={send.isPending} onClick={() => setConfirming(false)}>Keep editing</button>
            <button className="btn-primary" disabled={send.isPending} onClick={() => send.mutate()}>
              {send.isPending ? "Sending…" : "Send now"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

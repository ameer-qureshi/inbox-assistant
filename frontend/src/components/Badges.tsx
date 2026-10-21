import type { Category, EmailStatus } from "../api";
import { CATEGORY_LABEL, PRIORITY_LABEL, PRIORITY_STYLE, STATUS_LABEL } from "../format";

export function PriorityBadge({ priority }: { priority: number | null }) {
  if (!priority) return <span className="rounded px-1.5 py-0.5 text-xs text-ink-faint ring-1 ring-line">Not sorted yet</span>;
  const s = PRIORITY_STYLE[priority];
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${s.text} ${s.tint}`}>
      P{priority} {PRIORITY_LABEL[priority]}
    </span>
  );
}

export function CategoryBadge({ category }: { category: Category | null }) {
  if (!category) return null;
  return <span className="rounded px-1.5 py-0.5 text-xs font-medium text-ink-soft ring-1 ring-line">{CATEGORY_LABEL[category]}</span>;
}

const STATUS_STYLE: Record<EmailStatus, string> = {
  to_process: "text-ink",
  draft_ready: "text-post",
  replied: "text-ok",
  ignored: "text-ink-faint",
};

export function StatusText({ status }: { status: EmailStatus }) {
  return <span className={`text-xs font-medium ${STATUS_STYLE[status]}`}>{STATUS_LABEL[status]}</span>;
}

export function ReviewFlag() {
  return (
    <span className="rounded px-1.5 py-0.5 text-xs font-semibold text-p2 ring-1 ring-p2/40"
          title="The AI could not classify this email reliably">
      To verify
    </span>
  );
}

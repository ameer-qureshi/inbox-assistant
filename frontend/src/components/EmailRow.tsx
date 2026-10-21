import { Link, To } from "react-router-dom";
import type { EmailListItem } from "../api";
import { PRIORITY_STYLE, shortDate } from "../format";
import { CategoryBadge, PriorityBadge, ReviewFlag, StatusText } from "./Badges";

export default function EmailRow({ email, active, to }: { email: EmailListItem; active: boolean; to: To }) {
  const bar = email.priority ? PRIORITY_STYLE[email.priority].bar : "bg-line";
  const done = email.status === "replied" || email.status === "ignored";
  return (
    <Link to={to} aria-current={active ? "true" : undefined}
          className={`relative flex gap-3 py-3 pl-5 pr-4 hover:bg-desk/60 ${active ? "bg-post-tint" : ""}`}>
      {/* The priority "slot": the one strong visual cue of the list */}
      <span aria-hidden className={`absolute inset-y-0 left-0 w-1.5 ${bar} ${done ? "opacity-30" : ""}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className={`truncate text-sm ${done ? "font-medium text-ink-soft" : "font-bold"}`}>
            {email.from_name || email.from_address}
          </span>
          <time dateTime={email.received_at} className="ml-auto shrink-0 text-xs text-ink-soft">
            {shortDate(email.received_at)}
          </time>
        </div>
        <p className={`truncate text-sm ${done ? "text-ink-soft" : "font-medium"}`}>{email.subject || "(no subject)"}</p>
        <p className="truncate text-sm text-ink-soft">{email.ai_summary ?? email.snippet}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <PriorityBadge priority={email.priority} />
          <CategoryBadge category={email.category} />
          {email.needs_review && <ReviewFlag />}
          <span className="ml-auto"><StatusText status={email.status} /></span>
        </div>
      </div>
    </Link>
  );
}

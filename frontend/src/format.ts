import type { Category, EmailStatus } from "./api";

export const CATEGORY_LABEL: Record<Category, string> = {
  client: "Client",
  invoice: "Invoice",
  appointment: "Appointment",
  newsletter: "Newsletter",
  spam: "Probable spam",
  other: "Other",
};

export const STATUS_LABEL: Record<EmailStatus, string> = {
  to_process: "To process",
  draft_ready: "Draft ready",
  replied: "Replied",
  ignored: "Ignored",
};

export const PRIORITY_LABEL: Record<number, string> = { 1: "Urgent", 2: "This week", 3: "Low" };

// Tailwind class sets per priority (stripe, text, tint)
export const PRIORITY_STYLE: Record<number, { bar: string; text: string; tint: string }> = {
  1: { bar: "bg-p1", text: "text-p1", tint: "bg-p1-tint" },
  2: { bar: "bg-p2", text: "text-p2", tint: "bg-p2-tint" },
  3: { bar: "bg-p3", text: "text-p3", tint: "bg-p3-tint" },
};

const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

export function shortDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  if (sameDay(d, now)) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (sameDay(d, y)) return `Yesterday ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

export function longDate(iso: string): string {
  return new Date(iso).toLocaleString([], {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

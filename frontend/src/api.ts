// Typed client for the backend. The site only ever talks to /api (never to n8n).

export type Category = "client" | "invoice" | "appointment" | "newsletter" | "spam" | "other";
export type EmailStatus = "to_process" | "draft_ready" | "replied" | "ignored";
export type ReplyStatus = "sending" | "sent" | "failed";
export type Tone = "formal" | "neutral" | "short";

export interface EmailListItem {
  id: number;
  thread_id: number;
  from_name: string;
  from_address: string;
  subject: string;
  snippet: string;
  received_at: string;
  status: EmailStatus;
  category: Category | null;
  priority: number | null;
  ai_summary: string | null;
  needs_review: boolean;
  classification_state: "pending" | "done" | "fallback";
}

export interface EmailOut extends EmailListItem {
  to_addresses: string[];
  cc_addresses: string[];
  body_text: string;
  expected_action: string | null;
  is_outbound: boolean;
}

export interface Page<T> { items: T[]; total: number; page: number; page_size: number; pages: number }

export interface Reply {
  id: number; email_id: number; body: string; status: ReplyStatus; attempts: number;
  error: string | null; created_at: string; sent_at: string | null;
}

export interface Draft { id: number; email_id: number; tone: Tone; body: string; model: string; created_at: string }

export interface Thread { id: number; subject: string; messages: EmailOut[]; replies: Reply[]; latest_draft: Draft | null }

export interface Summary {
  date: string; total: number; to_process: number; high_priority: number;
  by_category: Record<string, number>; summary: string; ai_generated: boolean;
  top: { email: EmailListItem; reason: string }[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event("auth:expired"));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* not JSON */ }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export interface Filters {
  category?: string; priority?: string; status?: string; sender?: string;
  date_from?: string; date_to?: string; q?: string; page?: string;
}

export const api = {
  me: () => request<{ id: number; email: string }>("/auth/me"),
  login: (email: string, password: string) =>
    request<{ id: number; email: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),

  emails: (f: Filters) => {
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => { if (v) p.set(k, v); });
    p.set("page_size", "20");
    return request<Page<EmailListItem>>(`/emails?${p}`);
  },
  thread: (id: number) => request<Thread>(`/threads/${id}`),
  summary: () => request<Summary>("/summary"),
  setStatus: (id: number, status: "to_process" | "ignored") =>
    request<EmailOut>(`/emails/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  draft: (id: number, tone: Tone) =>
    request<Draft>(`/emails/${id}/draft`, { method: "POST", body: JSON.stringify({ tone }) }),
  reply: (id: number, body: string, idempotencyKey: string, draftId?: number) =>
    request<Reply>(`/emails/${id}/reply`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ body, draft_id: draftId ?? null }),
    }),
  retry: (replyId: number) => request<Reply>(`/replies/${replyId}/retry`, { method: "POST" }),
};

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

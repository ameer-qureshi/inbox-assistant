import { useState } from "react";
import type { Filters } from "../api";
import { CATEGORY_LABEL, PRIORITY_LABEL, STATUS_LABEL } from "../format";

interface Props { filters: Filters; onChange: (f: Filters) => void }

export default function FilterBar({ filters, onChange }: Props) {
  const active = (["category", "priority", "status", "sender", "date_from", "date_to"] as const)
    .filter((k) => filters[k]).length;
  const [open, setOpen] = useState(active > 0);

  // Changing any filter goes back to page 1
  const set = (key: keyof Filters, value: string) => onChange({ ...filters, [key]: value || undefined, page: undefined });

  return (
    <section className="border-b border-line bg-sheet px-4 py-2.5" aria-label="Filters">
      <div className="flex items-center gap-2">
        <button className="text-sm font-semibold text-post" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide filters" : "Filters"}{active > 0 ? ` (${active})` : ""}
        </button>
        {active > 0 && (
          <button className="ml-auto text-sm text-ink-soft underline"
                  onClick={() => onChange({ q: filters.q })}>Clear</button>
        )}
      </div>

      {open && (
        <div className="mt-2.5 grid grid-cols-2 gap-2.5 pb-1">
          <Select label="Category" value={filters.category} onChange={(v) => set("category", v)}
                  options={Object.entries(CATEGORY_LABEL)} />
          <Select label="Priority" value={filters.priority} onChange={(v) => set("priority", v)}
                  options={Object.entries(PRIORITY_LABEL).map(([k, v]) => [k, `P${k} ${v}`])} />
          <Select label="Status" value={filters.status} onChange={(v) => set("status", v)}
                  options={Object.entries(STATUS_LABEL)} />
          <label className="text-xs font-medium text-ink-soft">
            Sender
            <input className="field mt-1" placeholder="Name or address" defaultValue={filters.sender ?? ""}
                   key={filters.sender ?? ""}
                   onBlur={(e) => e.target.value !== (filters.sender ?? "") && set("sender", e.target.value.trim())}
                   onKeyDown={(e) => e.key === "Enter" && set("sender", (e.target as HTMLInputElement).value.trim())} />
          </label>
          <label className="text-xs font-medium text-ink-soft">
            From
            <input type="date" className="field mt-1" value={filters.date_from ?? ""}
                   onChange={(e) => set("date_from", e.target.value)} />
          </label>
          <label className="text-xs font-medium text-ink-soft">
            To
            <input type="date" className="field mt-1" value={filters.date_to ?? ""}
                   onChange={(e) => set("date_to", e.target.value)} />
          </label>
        </div>
      )}
    </section>
  );
}

function Select({ label, value, onChange, options }: {
  label: string; value?: string; onChange: (v: string) => void; options: [string, string][];
}) {
  return (
    <label className="text-xs font-medium text-ink-soft">
      {label}
      <select className="field mt-1" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

"use client";

// Controles pequenos e reutilizáveis do editor de templates.

export function Section({ title, children, open = true }: { title: string; children: React.ReactNode; open?: boolean }) {
  return (
    <details open={open} className="card group">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold">
        {title}
        <span className="text-zinc-500 transition group-open:rotate-180">⌄</span>
      </summary>
      <div className="space-y-3 border-t border-zinc-800 px-4 py-4">{children}</div>
    </details>
  );
}

export function Range({
  label, value, onChange, min, max, step = 1, suffix = "",
}: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number; suffix?: string;
}) {
  return (
    <label className="block text-xs text-zinc-400">
      <span className="flex justify-between">
        {label}
        <span className="font-mono text-zinc-200">{Number(value.toFixed(2))}{suffix}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full accent-violet-500" aria-label={label} />
    </label>
  );
}

export function Color({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs text-zinc-400">
      {label}
      <span className="flex items-center gap-2">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-7 w-9 cursor-pointer rounded border border-zinc-700 bg-transparent" aria-label={label} />
        <span className="w-16 font-mono text-[11px] text-zinc-300">{value}</span>
      </span>
    </label>
  );
}

export function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-2 text-xs text-zinc-300">
      {label}
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-violet-500" />
    </label>
  );
}

export function Choice<T extends string>({
  label, value, options, onChange,
}: { label?: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div>
      {label && <span className="label">{label}</span>}
      <div className="flex flex-wrap gap-1">
        {options.map((o) => (
          <button key={o.value} type="button" onClick={() => onChange(o.value)}
            className={`rounded-md border px-2 py-1 text-xs transition ${
              value === o.value ? "border-violet-500 bg-violet-500/15 text-white" : "border-zinc-700 text-zinc-300 hover:bg-zinc-800"}`}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

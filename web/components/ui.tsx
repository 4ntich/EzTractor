"use client";

// Controles pequenos e reutilizáveis do editor de templates (seguem as cores do tema).

const ACCENT = { accentColor: "rgb(var(--a-500))" } as const;

export function Section({ title, children, open = true }: { title: string; children: React.ReactNode; open?: boolean }) {
  return (
    <details open={open} className="card group">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold">
        {title}
        <span className="text-zinc-500 transition group-open:rotate-180">⌄</span>
      </summary>
      <div className="space-y-3 border-t border-white/10 px-4 py-4">{children}</div>
    </details>
  );
}

/** Grupo visual simples dentro de um painel. */
export function Group({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="space-y-3 rounded-xl border border-white/10 bg-black/10 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="label mb-0">{title}</span>
        {right}
      </div>
      {children}
    </div>
  );
}

export function Range({
  label, value, onChange, min, max, step = 1, suffix = "", disabled = false,
}: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number; suffix?: string;
  disabled?: boolean;
}) {
  return (
    <label className={`block text-xs text-zinc-400 ${disabled ? "opacity-40" : ""}`}>
      <span className="flex justify-between">
        {label}
        <span className="font-mono text-zinc-200">{Number(value.toFixed(2))}{suffix}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled} style={ACCENT}
        onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full" aria-label={label} />
    </label>
  );
}

/** Amostra de cor clicável (abre o seletor do sistema). */
export function Swatch({ value, onChange, label, disabled = false }: {
  value: string; onChange: (v: string) => void; label: string; disabled?: boolean;
}) {
  return (
    <label className={`relative inline-flex h-8 w-8 shrink-0 cursor-pointer overflow-hidden rounded-lg ring-1 ring-white/25 ${disabled ? "opacity-40" : ""}`}
      style={{ background: value }} title={`${label}: ${value}`}>
      <input type="color" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value.toUpperCase())}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0" aria-label={label} />
    </label>
  );
}

export function Color({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs text-zinc-400">
      {label}
      <span className="flex items-center gap-2">
        <span className="font-mono text-[11px] text-zinc-300">{value}</span>
        <Swatch value={value} onChange={onChange} label={label} />
      </span>
    </div>
  );
}

/** Interruptor (switch). */
export function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 text-xs text-zinc-300">
      {label}
      <span className="relative inline-flex h-5 w-9 shrink-0 items-center">
        <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)}
          className="peer sr-only" aria-label={label} />
        <span className="absolute inset-0 rounded-full bg-zinc-700 transition peer-checked:bg-[rgb(var(--a-500))] peer-focus-visible:ring-2 peer-focus-visible:ring-[rgb(var(--a-400))]" />
        <span className="absolute left-0.5 h-4 w-4 rounded-full bg-white shadow transition peer-checked:translate-x-4" />
      </span>
    </label>
  );
}

export function Choice<T extends string>({
  label, value, options, onChange,
}: { label?: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div>
      {label && <span className="label">{label}</span>}
      <div className="inline-flex flex-wrap gap-1 rounded-xl bg-black/20 p-1 ring-1 ring-white/10">
        {options.map((o) => (
          <button key={o.value} type="button" onClick={() => onChange(o.value)} aria-pressed={value === o.value}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
              value === o.value
                ? "bg-[rgb(var(--a-500)/.25)] text-white ring-1 ring-[rgb(var(--a-400)/.6)]"
                : "text-zinc-300 hover:bg-white/5"}`}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Abas horizontais do painel do editor. */
export function Tabs<T extends string>({ value, onChange, tabs }: {
  value: T; onChange: (v: T) => void; tabs: { value: T; label: string; icon?: string }[];
}) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto rounded-xl bg-black/20 p-1 ring-1 ring-white/10">
      {tabs.map((t) => (
        <button key={t.value} type="button" role="tab" aria-selected={value === t.value} onClick={() => onChange(t.value)}
          data-testid={`tab-${t.value}`}
          className={`flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-xs font-semibold transition ${
            value === t.value
              ? "bg-[rgb(var(--a-500)/.25)] text-white ring-1 ring-[rgb(var(--a-400)/.6)]"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"}`}>
          {t.icon && <span aria-hidden="true">{t.icon}</span>}
          {t.label}
        </button>
      ))}
    </div>
  );
}

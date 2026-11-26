"use client";

import { useEffect, useRef, useState } from "react";

export const THEMES = [
  { key: "aero", label: "Aero Turquesa", swatch: ["#0A5560", "#1684FF"] },
  { key: "violeta", label: "Violeta Neon", swatch: ["#14111F", "#8B5CF6"] },
  { key: "ouro", label: "Ouro Noir", swatch: ["#17130D", "#D4A02A"] },
  { key: "esmeralda", label: "Esmeralda", swatch: ["#072019", "#10B981"] },
  { key: "sunset", label: "Pôr do Sol", swatch: ["#26121D", "#F95D16"] },
] as const;

export type ThemeKey = (typeof THEMES)[number]["key"];
type Mode = "dark" | "light";

function apply(theme: string, mode: Mode) {
  const d = document.documentElement;
  d.setAttribute("data-theme", theme);
  d.setAttribute("data-mode", mode);
  try {
    localStorage.setItem("ezt-theme", theme);
    localStorage.setItem("ezt-mode", mode);
  } catch {
    /* armazenamento indisponível: vale só nesta visita */
  }
}

export default function ThemeSwitcher() {
  const [theme, setTheme] = useState<string>("aero");
  const [mode, setMode] = useState<Mode>("dark");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const d = document.documentElement;
    setTheme(d.getAttribute("data-theme") || "aero");
    setMode((d.getAttribute("data-mode") as Mode) || "dark");
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const choose = (t: string) => {
    setTheme(t);
    apply(t, mode);
  };
  const toggleMode = () => {
    const m = mode === "dark" ? "light" : "dark";
    setMode(m);
    apply(theme, m);
  };
  const current = THEMES.find((t) => t.key === theme) ?? THEMES[0];

  return (
    <div className="flex items-center gap-2" ref={ref}>
      <button type="button" onClick={toggleMode} className="btn-ghost h-9 w-9 px-0"
        aria-label={mode === "dark" ? "Mudar para modo claro" : "Mudar para modo escuro"}
        title={mode === "dark" ? "Modo claro" : "Modo escuro"} data-testid="toggle-mode">
        {mode === "dark" ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
          </svg>
        )}
      </button>
      <div className="relative">
        <button type="button" onClick={() => setOpen((o) => !o)} className="btn-ghost h-9 gap-2 px-3"
          aria-haspopup="listbox" aria-expanded={open} data-testid="theme-menu">
          <span className="flex h-4 w-4 overflow-hidden rounded-full ring-1 ring-white/40" aria-hidden="true">
            <span className="w-1/2" style={{ background: current.swatch[0] }} />
            <span className="w-1/2" style={{ background: current.swatch[1] }} />
          </span>
          <span className="hidden text-xs sm:inline">{current.label}</span>
        </button>
        {open && (
          <ul role="listbox" aria-label="Tema"
            className="card menu-pop ezt-rise absolute right-0 z-50 mt-2 w-52 p-1.5">
            {THEMES.map((t) => (
              <li key={t.key}>
                <button type="button" role="option" aria-selected={t.key === theme} onClick={() => { choose(t.key); setOpen(false); }}
                  className={`flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left text-sm transition hover:bg-white/10 ${
                    t.key === theme ? "bg-violet-500/15 text-white" : "text-zinc-200"}`}
                  data-testid={`theme-${t.key}`}>
                  <span className="flex h-5 w-5 overflow-hidden rounded-full ring-1 ring-white/30" aria-hidden="true">
                    <span className="w-1/2" style={{ background: t.swatch[0] }} />
                    <span className="w-1/2" style={{ background: t.swatch[1] }} />
                  </span>
                  {t.label}
                  {t.key === "aero" && <span className="ml-auto text-[10px] text-zinc-400">padrão</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

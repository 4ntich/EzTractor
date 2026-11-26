"use client";

import { useEffect, useRef, useState } from "react";

import { api as apiFetch, UpdateInfo } from "@/lib/api";

type Pywebview = {
  api: { open_videos: () => void; open_config: () => void; open_browser: () => void; quit: () => void };
};

export default function DesktopMenu() {
  const [open, setOpen] = useState(false);
  const [has, setHas] = useState(false);
  const [checking, setChecking] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  async function checkUpdate() {
    setOpen(false);
    setChecking(true);
    try {
      const u = await apiFetch<UpdateInfo>("/system/update?force=true");
      if (u.error) {
        alert(`Não foi possível verificar agora.\n${u.error}`);
      } else if (!u.available) {
        alert(`Você já está na versão mais recente (${u.current}).`);
      } else if (u.can_install) {
        if (confirm(`Nova versão ${u.latest} disponível (você tem ${u.current}).\n\nBaixar e instalar agora? O EzTractor vai fechar e reabrir sozinho.`)) {
          await apiFetch("/system/update/install", { method: "POST" });
          alert("Baixando a atualização… O app vai reabrir quando terminar. Acompanhe pela barra no topo.");
        }
      } else {
        alert(`Nova versão ${u.latest} disponível. Baixe pela página de Releases do GitHub.`);
      }
    } catch {
      alert("Não foi possível verificar atualizações agora.");
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    const check = () => setHas(typeof (window as unknown as { pywebview?: Pywebview }).pywebview !== "undefined");
    check();
    const t = setInterval(check, 500); // o pywebview injeta a API logo após carregar
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!has) return null;
  const api = (window as unknown as { pywebview: Pywebview }).pywebview.api;
  const call = (fn: () => void) => { fn(); setOpen(false); };

  const items: [string, () => void][] = [
    ["🔄  Verificar atualizações", checkUpdate],
    ["📁  Pasta dos vídeos", api.open_videos],
    ["⚙️  Configurações", api.open_config],
    ["🌐  Abrir no navegador", api.open_browser],
    ["⏻  Sair", api.quit],
  ];

  return (
    <div className="relative" ref={ref}>
      <button type="button" className="btn-ghost h-9 px-3 text-sm" aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen((o) => !o)} disabled={checking} data-testid="desktop-menu">
        {checking ? "Verificando…" : "Menu"}
      </button>
      {open && (
        <ul role="menu" className="card menu-pop ezt-rise absolute right-0 z-50 mt-2 w-56 p-1.5">
          {items.map(([label, fn]) => (
            <li key={label}>
              <button role="menuitem" className="w-full rounded-lg px-3 py-2 text-left text-sm text-zinc-200 transition hover:bg-white/10"
                onClick={() => call(fn)}>
                {label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

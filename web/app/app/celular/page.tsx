"use client";

import { useCallback, useEffect, useState } from "react";

import { api, API_URL, SystemInfo } from "@/lib/api";

export default function CelularPage() {
  const [sys, setSys] = useState<SystemInfo | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(() => api<SystemInfo>("/system/info").then(setSys).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  async function save(enabled: boolean) {
    setBusy(true);
    setMsg(null);
    try {
      await api("/system/lan", { method: "POST", body: JSON.stringify({ enabled, password: password || null }) });
      setPassword("");
      setMsg({ ok: true, text: "Salvo. Reinicie o EzTractor para aplicar." });
      load();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Erro" });
    } finally {
      setBusy(false);
    }
  }

  async function restart() {
    setBusy(true);
    try {
      await api("/system/restart", { method: "POST" });
      setMsg({ ok: true, text: "Reiniciando o EzTractor…" });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Reinicie o app manualmente." });
      setBusy(false);
    }
  }

  if (!sys) return <p className="text-sm text-zinc-400">Carregando…</p>;
  const url = sys.lan.urls[0];

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Usar no celular</h1>
        <p className="mt-1 text-sm text-zinc-400">
          O celular acessa o EzTractor que roda neste computador, pelo mesmo Wi-Fi. O processamento continua no PC;
          o celular só mostra a tela e envia os comandos.
        </p>
      </header>

      <section className="card space-y-4 p-5">
        <label className="flex items-center justify-between gap-3">
          <span className="font-semibold text-white">Liberar acesso pelo celular (rede local)</span>
          <input type="checkbox" className="h-5 w-5 accent-violet-500" checked={sys.lan.enabled}
            onChange={(e) => (e.target.checked ? save(true) : save(false))} disabled={busy}
            data-testid="lan-toggle" />
        </label>

        <div>
          <label className="label" htmlFor="pw">Senha de acesso {sys.lan.password_set && "(já definida)"}</label>
          <input id="pw" type="text" className="input" placeholder={sys.lan.password_set ? "•••••• (deixe em branco para manter)" : "crie uma senha (mín. 6)"}
            value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="mt-1 text-xs text-zinc-500">
            O acesso pelo celular sempre exige senha, para ninguém mais na sua rede entrar. Aqui no computador o app
            não pede senha.
          </p>
        </div>
        {!sys.lan.configurable && (
          <p className="text-xs text-amber-300">As configurações só podem ser alteradas no app instalado (Windows).</p>
        )}
        {msg && <p className={`rounded-lg px-3 py-2 text-sm ${msg.ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-danger"}`}>{msg.text}</p>}
        {sys.lan.configurable && sys.can_restart && (
          <button className="btn-ghost w-fit text-xs" onClick={restart} disabled={busy}>Reiniciar o EzTractor agora</button>
        )}
      </section>

      {sys.lan.enabled && url && (
        <section className="card space-y-4 p-5">
          <h2 className="font-semibold text-white">Abrir no celular</h2>
          <div className="flex flex-wrap items-center gap-5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img alt="QR code para abrir no celular" width={168} height={168}
              className="rounded-xl bg-white p-2"
              src={`${API_URL}/system/qr.svg?data=${encodeURIComponent(url)}`} data-testid="qr" />
            <div className="min-w-0 space-y-2 text-sm">
              <p className="text-zinc-300">1. Conecte o celular no mesmo Wi-Fi.</p>
              <p className="text-zinc-300">2. Aponte a câmera para o QR, ou digite no navegador:</p>
              <ul className="space-y-1">
                {sys.lan.urls.map((u) => (
                  <li key={u}><code className="rounded bg-zinc-900/60 px-2 py-1 text-violet-200">{u}</code></li>
                ))}
              </ul>
              <p className="text-zinc-300">3. Entre com a senha. No celular, use “Adicionar à tela inicial” para virar um atalho.</p>
            </div>
          </div>
          <p className="text-xs text-zinc-500">
            Se não abrir, o firewall do Windows pode estar bloqueando. Autorize o EzTractor nas redes privadas quando perguntado.
          </p>
        </section>
      )}

      <p className="text-xs text-zinc-500">Versão {sys.version}. Deixe o computador ligado e o EzTractor aberto enquanto usar pelo celular.</p>
    </div>
  );
}

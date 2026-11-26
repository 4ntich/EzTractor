"use client";

import { useCallback, useEffect, useState } from "react";

import { Toggle } from "@/components/ui";
import { api, API_URL, LanInfo, SystemInfo } from "@/lib/api";

const ago = (s: number) => (s < 15 ? "ativo agora" : s < 60 ? `há ${s} s` : `há ${Math.round(s / 60)} min`);
const icon = (d: string) => (d === "iPhone" || d === "Android" ? "📱" : d === "iPad" ? "📲" : "💻");

export default function CelularPage() {
  const [sys, setSys] = useState<SystemInfo | null>(null);
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [editing, setEditing] = useState(false); // formulário de senha aberto (criar ou redefinir)
  const [enableAfterSave, setEnableAfterSave] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(() => api<SystemInfo>("/system/info").then(setSys).catch(() => {}), []);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000); // aparelhos conectados
    return () => clearInterval(t);
  }, [load]);

  const setLan = (lan: LanInfo) => setSys((s) => (s ? { ...s, lan } : s));

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Erro" });
    } finally {
      setBusy(false);
    }
  }

  const afterEnable = (restart: boolean) =>
    setMsg({ ok: true, text: restart
      ? "Acesso liberado. Reinicie o EzTractor para os aparelhos da rede conseguirem abrir."
      : "Acesso liberado." });

  function toggleLan(on: boolean) {
    if (on && !sys?.lan.password_set) { // precisa de senha antes
      setEditing(true);
      setEnableAfterSave(true);
      setMsg({ ok: false, text: "Crie uma senha para liberar o acesso pelo celular." });
      return;
    }
    run(async () => {
      const r = await api<{ restart_required: boolean }>("/system/lan", { method: "POST", body: JSON.stringify({ enabled: on }) });
      await load();
      if (on) afterEnable(r.restart_required);
      else setMsg({ ok: true, text: "Acesso pelo celular desligado. Quem estava conectado foi desconectado." });
    });
  }

  function savePassword() {
    const enabled = Boolean(sys?.lan.enabled || enableAfterSave);
    const redefining = Boolean(sys?.lan.password_set);
    run(async () => {
      const r = await api<{ restart_required: boolean }>("/system/lan", {
        method: "POST", body: JSON.stringify({ enabled, password }),
      });
      setPassword("");
      setEditing(false);
      setEnableAfterSave(false);
      await load();
      if (enableAfterSave) afterEnable(r.restart_required);
      else setMsg({ ok: true, text: redefining
        ? "Senha redefinida. Quem estava conectado com a senha antiga precisa entrar de novo."
        : "Senha salva." });
    });
  }

  function deletePassword() {
    run(async () => {
      setLan(await api<LanInfo>("/system/lan/password", { method: "DELETE" }));
      setConfirmDelete(false);
      setMsg({ ok: true, text: "Senha excluída. O acesso pelo celular foi desligado e quem estava conectado saiu." });
    });
  }

  function disconnect() {
    run(async () => {
      setLan(await api<LanInfo>("/system/lan/disconnect", { method: "POST" }));
      setMsg({ ok: true, text: "Conexões encerradas. Para voltar, o aparelho vai precisar digitar a senha de novo." });
    });
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
  const { lan } = sys;
  const [mainUrl, ...otherUrls] = lan.urls;
  const formOpen = editing || !lan.password_set;
  const locked = !lan.configurable || busy;

  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Usar no celular</h1>
        <p className="mt-1 text-sm text-zinc-400">
          O celular acessa o EzTractor que roda neste computador, pelo mesmo Wi-Fi. O processamento continua no PC;
          o celular só mostra a tela e envia os comandos.
        </p>
      </header>

      <section className="card space-y-5 p-5">
        <div className="[&_label]:text-sm [&_label]:font-semibold [&_label]:text-white" data-testid="lan-toggle">
          <Toggle label="Liberar acesso pelo celular (rede local)" checked={lan.enabled} onChange={(v) => !locked && toggleLan(v)} />
        </div>

        <div className="space-y-3 rounded-xl bg-black/10 p-4 ring-1 ring-white/10">
          <span className="label mb-0">Senha de acesso</span>

          {lan.password_set && !editing ? (
            <div className="flex flex-wrap items-center gap-3" data-testid="pw-set">
              <span className="inline-flex items-center gap-2 rounded-lg bg-emerald-500/15 px-3 py-1.5 text-sm font-medium text-emerald-300 ring-1 ring-emerald-400/30">
                ✓ Senha já definida
              </span>
              <div className="ml-auto flex flex-wrap gap-2">
                <button className="btn-ghost h-9 px-3 text-xs" disabled={locked}
                  onClick={() => { setEditing(true); setConfirmDelete(false); setMsg(null); }}>Redefinir senha</button>
                <button className="btn-ghost h-9 px-3 text-xs text-danger" disabled={locked}
                  onClick={() => setConfirmDelete(true)}>Excluir senha</button>
              </div>
            </div>
          ) : formOpen && (
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (password.length >= 6) savePassword(); }}>
              <div className="flex flex-wrap gap-2">
                <div className="relative min-w-[200px] flex-1">
                  <input type={showPw ? "text" : "password"} className="input pr-10" autoComplete="new-password"
                    placeholder={lan.password_set ? "nova senha (mín. 6)" : "crie uma senha (mín. 6)"} aria-label="Senha"
                    value={password} onChange={(e) => setPassword(e.target.value)} disabled={locked} />
                  <button type="button" onClick={() => setShowPw((v) => !v)} title={showPw ? "Esconder" : "Mostrar"}
                    className="absolute inset-y-0 right-2 text-sm text-zinc-400 hover:text-white">{showPw ? "🙈" : "👁"}</button>
                </div>
                <button type="submit" className="btn h-10" disabled={locked || password.length < 6}>
                  {enableAfterSave ? "Salvar e liberar" : lan.password_set ? "Salvar nova senha" : "Salvar senha"}
                </button>
                {lan.password_set && (
                  <button type="button" className="btn-ghost h-10" onClick={() => { setEditing(false); setPassword(""); }}>Cancelar</button>
                )}
              </div>
              {password.length > 0 && password.length < 6 && <p className="text-xs text-amber-300">Mínimo de 6 caracteres.</p>}
            </form>
          )}

          {confirmDelete && (
            <div className="space-y-2 rounded-lg bg-red-500/10 p-3 ring-1 ring-red-400/30" data-testid="confirm-delete">
              <p className="text-sm text-red-200">
                Excluir a senha também <b>desliga o acesso pelo celular</b> e desconecta quem estiver usando. Continuar?
              </p>
              <div className="flex gap-2">
                <button className="btn-ghost h-9 px-3 text-xs text-danger" onClick={deletePassword} disabled={busy}>Sim, excluir senha</button>
                <button className="btn-ghost h-9 px-3 text-xs" onClick={() => setConfirmDelete(false)}>Cancelar</button>
              </div>
            </div>
          )}

          <p className="text-xs text-zinc-500">
            O acesso pelo celular sempre exige senha, para ninguém mais na sua rede entrar. Aqui no computador o app não pede senha.
          </p>
        </div>

        {!lan.configurable && (
          <p className="text-xs text-amber-300">As configurações só podem ser alteradas no app instalado (Windows).</p>
        )}
        {msg && (
          <p role="status" className={`rounded-lg px-3 py-2 text-sm ${msg.ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-danger"}`}>
            {msg.text}
          </p>
        )}
        {lan.restart_required && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-amber-500/10 px-3 py-2 ring-1 ring-amber-400/30">
            <p className="text-sm text-amber-200">Falta reiniciar o EzTractor para o acesso pela rede começar a funcionar.</p>
            {sys.can_restart && <button className="btn h-9 px-3 text-xs" onClick={restart} disabled={busy}>Reiniciar agora</button>}
          </div>
        )}
      </section>

      {lan.enabled && lan.password_set && !lan.restart_required && (
        <section className="card space-y-3 p-5" data-testid="devices">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold text-white">Aparelhos conectados</h2>
            {lan.devices.length > 0 && (
              <button className="btn-ghost h-9 px-3 text-xs text-danger" onClick={disconnect} disabled={busy} data-testid="disconnect">
                Encerrar conexões
              </button>
            )}
          </div>
          {lan.devices.length === 0 ? (
            <p className="text-sm text-zinc-500">Nenhum aparelho conectado agora.</p>
          ) : (
            <ul className="space-y-1.5">
              {lan.devices.map((d) => (
                <li key={d.ip} className="flex items-center gap-3 rounded-lg bg-white/5 px-3 py-2 text-sm ring-1 ring-white/10">
                  <span aria-hidden="true">{icon(d.device)}</span>
                  <span className="font-medium text-white">{d.device}</span>
                  <code className="text-xs text-zinc-400">{d.ip}</code>
                  <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-emerald-300">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />{ago(d.seconds_ago)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {lan.enabled && mainUrl && !lan.restart_required && (
        <section className="card space-y-4 p-5">
          <h2 className="font-semibold text-white">Abrir no celular</h2>
          <div className="flex flex-wrap items-center gap-5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img alt="QR code para abrir no celular" width={168} height={168}
              className="rounded-xl bg-white p-2"
              src={`${API_URL}/system/qr.svg?data=${encodeURIComponent(mainUrl)}`} data-testid="qr" />
            <div className="min-w-0 space-y-2 text-sm">
              <p className="text-zinc-300">1. Conecte o celular no mesmo Wi-Fi.</p>
              <p className="text-zinc-300">2. Aponte a câmera para o QR, ou digite no navegador:</p>
              <code className="inline-block rounded bg-zinc-900/60 px-2 py-1 text-[rgb(var(--a-200))]" data-testid="main-url">{mainUrl}</code>
              <p className="text-zinc-300">3. Entre com a senha. No celular, use “Adicionar à tela inicial” para virar um atalho.</p>
            </div>
          </div>
          {otherUrls.length > 0 && (
            <details className="text-xs text-zinc-500">
              <summary className="cursor-pointer">Outros endereços deste PC (só se o de cima não abrir)</summary>
              <p className="mt-2">Normalmente são placas de rede virtuais (VirtualBox, WSL, Docker) que o celular não alcança.</p>
              <ul className="mt-1 space-y-1">
                {otherUrls.map((u) => <li key={u}><code>{u}</code></li>)}
              </ul>
            </details>
          )}
          <p className="text-xs text-zinc-500">
            Se não abrir, o firewall do Windows pode estar bloqueando. Autorize o EzTractor nas redes privadas quando perguntado.
          </p>
        </section>
      )}

      <p className="text-xs text-zinc-500">Versão {sys.version}. Deixe o computador ligado e o EzTractor aberto enquanto usar pelo celular.</p>
    </div>
  );
}

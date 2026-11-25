"use client";

import { useEffect, useRef, useState } from "react";

import { api, UpdateInfo } from "@/lib/api";

export default function UpdateBanner() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [busy, setBusy] = useState(false);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api<UpdateInfo>("/system/update").then(setInfo).catch(() => {});
    return () => { if (poll.current) clearInterval(poll.current); };
  }, []);

  async function update() {
    setBusy(true);
    try {
      await api<UpdateInfo>("/system/update/install", { method: "POST" });
      poll.current = setInterval(async () => {
        try {
          setInfo(await api<UpdateInfo>("/system/update/progress"));
        } catch {
          // o app está reiniciando: para de poluir o console
          if (poll.current) clearInterval(poll.current);
        }
      }, 700);
    } catch (e) {
      setInfo((i) => (i ? { ...i, status: "error", error: e instanceof Error ? e.message : "falha" } : i));
      setBusy(false);
    }
  }

  if (!info || !info.available || dismissed) return null;
  const working = info.status === "downloading" || info.status === "installing";

  return (
    <div className="card mb-5 flex flex-wrap items-center gap-3 border-l-4 border-l-violet-400 p-4" role="status">
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-white">
          Atualização disponível: <span className="text-gradient">{info.latest}</span>
          <span className="ml-2 text-xs font-normal text-zinc-400">(você tem {info.current})</span>
        </p>
        {working ? (
          <div className="mt-2">
            <div className="h-2 overflow-hidden rounded-full bg-zinc-800 ring-1 ring-white/10">
              <div className="h-full bg-brand transition-all" style={{ width: `${info.progress}%` }} />
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              {info.status === "downloading" ? `Baixando… ${info.progress}%` : "Instalando e reabrindo o EzTractor…"}
            </p>
          </div>
        ) : info.status === "error" ? (
          <p className="mt-1 text-sm text-danger">{info.error}</p>
        ) : (
          info.notes && <p className="mt-1 line-clamp-2 text-xs text-zinc-400">{info.notes}</p>
        )}
      </div>
      {!working && (
        <div className="flex gap-2">
          {info.can_install ? (
            <button className="btn" onClick={update} disabled={busy} data-testid="do-update">
              {busy ? "Aguarde…" : "Atualizar agora"}
            </button>
          ) : (
            info.page && <a className="btn" href={info.page} target="_blank" rel="noreferrer">Ver atualização</a>
          )}
          <button className="btn-ghost" onClick={() => setDismissed(true)}>Depois</button>
        </div>
      )}
    </div>
  );
}

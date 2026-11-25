"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useMe } from "@/components/AppShell";
import ClipCard from "@/components/ClipCard";
import StatusBadge from "@/components/StatusBadge";
import { api, fmtTime, Project } from "@/lib/api";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { refresh: refreshMe } = useMe();
  const [p, setP] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Project>(`/projects/${id}`)
      .then(setP)
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const busy = p && (p.status === "queued" || p.status === "processing");
  const rendering = p?.clips.some((c) => c.render_status === "pending");
  useEffect(() => {
    if (!busy && !rendering) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [busy, rendering, load]);

  useEffect(() => {
    if (p?.status === "ready" || p?.status === "failed") refreshMe();
  }, [p?.status, refreshMe]);

  async function reprocess() {
    await api(`/projects/${id}/reprocess`, { method: "POST" });
    load();
  }

  async function remove() {
    if (!confirm("Excluir este projeto e todos os clipes?")) return;
    await api(`/projects/${id}`, { method: "DELETE" });
    router.push("/app");
  }

  if (error) return <p className="text-red-400">{error}</p>;
  if (!p) return <p className="text-sm text-zinc-500">Carregando…</p>;

  return (
    <div className="space-y-6">
      <Link href="/app" className="text-sm text-zinc-400 hover:text-zinc-100">← Projetos</Link>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-bold">{p.title}</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {p.duration_s ? `${fmtTime(p.duration_s)} de vídeo · ` : ""}
            {p.credits_charged} crédito(s) · layout {p.settings.layout}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge p={p} />
          {(p.status === "ready" || p.status === "failed") && (
            <button className="btn-ghost" onClick={reprocess}>Reprocessar</button>
          )}
          {!busy && <button className="btn-ghost text-red-300" onClick={remove}>Excluir</button>}
        </div>
      </header>

      {busy && (
        <div className="card p-5">
          <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
            <div className="h-full bg-brand transition-all" style={{ width: `${p.progress}%` }} />
          </div>
          <p className="mt-3 text-sm text-zinc-400">
            Pode fechar esta página: o processamento continua no servidor.
          </p>
        </div>
      )}

      {p.status === "failed" && (
        <p className="rounded-lg bg-red-950 px-4 py-3 text-sm text-red-300">
          {p.error ?? "Falha no processamento"}. Seus créditos foram devolvidos.
        </p>
      )}

      {p.clips.length > 0 && (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {p.clips.map((c, i) => (
            <ClipCard key={`${c.id}-${c.start_s}-${c.end_s}-${c.render_status}`} clip={c} rank={i + 1} onChange={load} />
          ))}
        </section>
      )}
    </div>
  );
}

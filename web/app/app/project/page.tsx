"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import ClipCard from "@/components/ClipCard";
import StatusBadge from "@/components/StatusBadge";
import { api, fmtTime, Project } from "@/lib/api";
import type { Template } from "@/lib/templates";

function ProjectView() {
  const id = useSearchParams().get("id") ?? "";
  const router = useRouter();
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

  const [templates, setTemplates] = useState<Template[]>([]);
  const [tplChoice, setTplChoice] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  useEffect(() => {
    api<Template[]>("/templates").then(setTemplates).catch(() => {});
  }, []);
  const currentTpl = (p?.settings.template_id as string | null | undefined) ?? "";
  const chosenTpl = tplChoice ?? currentTpl;

  async function applyTemplate() {
    setApplying(true);
    try {
      await api(`/projects/${id}/apply-template`, {
        method: "POST",
        body: JSON.stringify({ template_id: chosenTpl || null }),
      });
      setTplChoice(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao aplicar o template");
    } finally {
      setApplying(false);
    }
  }

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
            layout {p.settings.layout}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge p={p} />
          {(p.status === "ready" || p.status === "failed") && (
            <button className="btn-ghost" onClick={reprocess}>Reprocessar</button>
          )}
          {!busy && <button className="btn-ghost text-danger" onClick={remove}>Excluir</button>}
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
          {p.error ?? "Falha no processamento"}
        </p>
      )}

      {p.status === "ready" && p.clips.length > 0 && (
        <div className="card flex flex-wrap items-end gap-3 p-4">
          <div className="min-w-[220px] flex-1">
            <label className="label" htmlFor="apply-tpl">Template dos clipes</label>
            <select id="apply-tpl" className="input" value={chosenTpl} onChange={(e) => setTplChoice(e.target.value)}>
              <option value="">Sem template (estilo simples)</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_default ? " (padrão)" : ""}</option>)}
            </select>
          </div>
          <button className="btn" onClick={applyTemplate} disabled={applying || rendering}>
            {applying ? "Aplicando…" : chosenTpl === currentTpl ? "Renderizar todos de novo" : "Aplicar a todos os clipes"}
          </button>
          <Link href="/app/templates" className="btn-ghost">Editar templates</Link>
        </div>
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

export default function ProjectPage() {
  return (
    <Suspense>
      <ProjectView />
    </Suspense>
  );
}

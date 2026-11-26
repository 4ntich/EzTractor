"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import ClipCard from "@/components/ClipCard";
import ClipEditor from "@/components/ClipEditor";
import CopyCaption from "@/components/CopyCaption";
import StatusBadge from "@/components/StatusBadge";
import { api, fileUrl, fmtTime, isBusy, Project, RENDER_QUALITIES } from "@/lib/api";
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

  const busy = p ? isBusy(p) : false;
  const [acting, setActing] = useState(false);

  async function control(action: "pause" | "resume" | "cancel") {
    if (action === "cancel" && !confirm("Cancelar o processamento? Os clipes já prontos são mantidos.")) return;
    setActing(true);
    try {
      setP(await api<Project>(`/projects/${id}/${action}`, { method: "POST" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha");
    } finally {
      setActing(false);
    }
  }
  const rendering = p?.clips.some((c) => c.render_status === "pending");
  useEffect(() => {
    if (!busy && !rendering) return;
    const t = setInterval(load, 1500);
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
            {p.settings.mode === "download" ? "Só download" : "Cortes com IA"}
            {p.duration_s ? ` · ${fmtTime(p.duration_s)} de vídeo` : ""}
            {p.settings.render_height
              ? ` · ${RENDER_QUALITIES.find((q) => q.value === p.settings.render_height)?.label.split(" ·")[0] ?? ""}`
              : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge p={p} />
          {p.source_file_url && (
            <a className="btn-ghost" href={fileUrl(p.source_file_url)} download data-testid="download-original">
              ⬇ Vídeo original
            </a>
          )}
          {(p.status === "ready" || p.status === "failed" || p.status === "cancelled") && (
            <button className="btn-ghost" onClick={reprocess}>Reprocessar</button>
          )}
          {!busy && <button className="btn-ghost text-danger" onClick={remove}>Excluir</button>}
        </div>
      </header>

      {busy && (
        <div className="card space-y-4 p-5">
          <div className="flex items-center justify-between gap-3 text-sm">
            <StatusBadge p={p} />
            <span className="font-mono text-zinc-300">{p.progress}%</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-zinc-800/80 ring-1 ring-white/10">
            <div className={`h-full rounded-full transition-all ${p.status === "paused" ? "bg-sky-400/70" : "bg-brand"}`}
              style={{ width: `${p.progress}%`, boxShadow: "0 0 12px rgb(var(--a-400) / .6)" }} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {p.status === "paused" || p.control === "pause" ? (
              <button className="btn" onClick={() => control("resume")} disabled={acting || p.control === "cancel"}
                data-testid="btn-resume">▶ Continuar</button>
            ) : (
              <button className="btn-ghost" onClick={() => control("pause")} disabled={acting || p.control === "cancel"}
                data-testid="btn-pause">⏸ Pausar</button>
            )}
            <button className="btn-ghost text-danger" onClick={() => control("cancel")}
              disabled={acting || p.control === "cancel"} data-testid="btn-cancel">✕ Cancelar</button>
            <span className="text-xs text-zinc-400">
              {p.status === "paused"
                ? "Pausado: nada está sendo processado. Continue quando quiser."
                : "Pode fechar esta página: o processamento continua."}
            </span>
          </div>
        </div>
      )}

      {p.status === "cancelled" && (
        <p className="rounded-xl bg-zinc-500/10 px-4 py-3 text-sm text-zinc-300 ring-1 ring-zinc-400/20">
          Processamento cancelado. {p.clips.length ? "Os clipes que já estavam prontos foram mantidos. " : ""}
          Use <b>Reprocessar</b> para começar de novo.
        </p>
      )}

      {(p.skip_segments?.length ?? 0) > 0 && (
        <details className="card px-4 py-3 text-sm">
          <summary className="cursor-pointer text-zinc-200">
            ⏭ {p.skip_segments!.length} trecho(s) de propaganda, inscrição ou final detectados e pulados
          </summary>
          <ul className="mt-2 space-y-1 text-zinc-400">
            {p.skip_segments!.map((s, i) => (
              <li key={i}>
                {fmtTime(s.start)}–{fmtTime(s.end)} · {s.reason}
                <span className="ml-1 text-xs text-zinc-500">({s.source === "sponsorblock" ? "SponsorBlock" : "fala detectada"})</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {p.settings.mode === "download" && p.status === "ready" && p.clips[0] && (
        <DownloadResult project={p} onChange={load} />
      )}

      {p.status === "failed" && (
        <p className="rounded-xl bg-red-500/15 px-4 py-3 text-sm text-danger ring-1 ring-red-400/30">
          {p.error ?? "Falha no processamento"}
        </p>
      )}

      {p.status === "ready" && (p.clips.length > 0 || p.settings.mode === "download") && (
        <div className="card flex flex-wrap items-end gap-3 p-4">
          <div className="min-w-[220px] flex-1">
            <label className="label" htmlFor="apply-tpl">{p.settings.mode === "download" ? "Template do vídeo" : "Template dos clipes"}</label>
            <select id="apply-tpl" className="input" value={chosenTpl} onChange={(e) => setTplChoice(e.target.value)}>
              <option value="">{p.settings.mode === "download" ? "Sem template (vídeo original)" : "Sem template (estilo simples)"}</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_default ? " (padrão)" : ""}</option>)}
            </select>
          </div>
          <button className="btn" onClick={applyTemplate} disabled={applying || rendering}>
            {applying ? "Aplicando…" : chosenTpl === currentTpl ? "Renderizar de novo"
              : p.settings.mode === "download" ? "Aplicar ao vídeo" : "Aplicar a todos os clipes"}
          </button>
          <Link href="/app/templates" className="btn-ghost">Editar templates</Link>
        </div>
      )}

      {p.clips.length > 0 && p.settings.mode !== "download" && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-bold">Clipes ({p.clips.length})</h2>
          <DownloadAll project={p} />
        </div>
      )}
      {p.clips.length > 0 && p.settings.mode !== "download" && (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {p.clips.map((c, i) => (
            <ClipCard key={`${c.id}-${c.start_s}-${c.end_s}-${c.render_status}`} clip={c} rank={i + 1} project={p} onChange={load} />
          ))}
        </section>
      )}
    </div>
  );
}

function DownloadAll({ project }: { project: Project }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = project.clips.filter((c) => c.render_status === "ready").length;

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const { url } = await api<{ url: string }>(`/projects/${project.id}/download-all`);
      const a = document.createElement("a"); // mesmo jeito dos botões "Baixar" de cada clipe
      a.href = fileUrl(url)!;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível baixar");
    } finally {
      setTimeout(() => setBusy(false), 1500); // o zip começa a baixar em seguida
    }
  }

  return (
    <div className="flex items-center gap-3">
      {error && <span className="text-xs text-danger">{error}</span>}
      <button className="btn" onClick={go} disabled={busy || ready === 0} data-testid="download-all"
        title={ready < project.clips.length ? `${project.clips.length - ready} clipe(s) ainda renderizando ficam de fora` : undefined}>
        {busy ? "Preparando…" : `⬇ Baixar todos (${ready})`}
      </button>
    </div>
  );
}

function DownloadResult({ project, onChange }: { project: Project; onChange: () => void }) {
  const c = project.clips[0];
  const [editing, setEditing] = useState(false);
  const cut = (c.cuts ?? []).reduce((a, [x, y]) => a + (y - x), 0);
  return (
    <div className="card overflow-hidden">
      {c.render_status === "ready" && c.video_url ? (
        <video key={c.video_url} src={fileUrl(c.video_url)} controls preload="metadata"
          className="max-h-[60vh] w-full bg-black" data-testid="result-player" />
      ) : (
        <div className="flex h-48 items-center justify-center text-sm text-zinc-400">
          {c.render_status === "failed" ? "Falha ao gerar o vídeo" : "Gerando o vídeo editado…"}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4">
        <p className="text-sm text-zinc-300">
          {fmtTime(c.start_s)}–{fmtTime(c.end_s)} · duração final {fmtTime(c.end_s - c.start_s - cut)}
          {(c.cuts?.length ?? 0) > 0 && <span className="text-red-300"> · {c.cuts!.length} corte(s)</span>}
        </p>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => setEditing(true)} disabled={c.render_status === "pending"}
            data-testid="edit-download">✂ Editar / cortar</button>
          {c.download_url && <a className="btn" href={fileUrl(c.download_url)} download>⬇ Baixar vídeo</a>}
        </div>
      </div>
      <div className="max-w-xl px-4 pb-4"><CopyCaption clip={c} /></div>
      {editing && <ClipEditor clip={c} project={project} onClose={() => setEditing(false)} onSaved={onChange} />}
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

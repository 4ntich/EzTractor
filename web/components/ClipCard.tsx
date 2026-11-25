"use client";

import { useState } from "react";

import { api, Clip, fileUrl, fmtTime, RANKER_LABEL } from "@/lib/api";

function scoreColor(score: number) {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 60) return "bg-amber-500";
  return "bg-zinc-600";
}

export default function ClipCard({ clip, rank, onChange }: { clip: Clip; rank: number; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [start, setStart] = useState(clip.start_s);
  const [end, setEnd] = useState(clip.end_s);
  const [title, setTitle] = useState(clip.title);
  const [hook, setHook] = useState(clip.hook);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api(`/clips/${clip.id}`, {
        method: "PATCH",
        body: JSON.stringify({ start_s: start, end_s: end, title, hook }),
      });
      setEditing(false);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao salvar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card flex flex-col overflow-hidden">
      <div className="relative aspect-[9/16] bg-black">
        {clip.render_status === "ready" && clip.video_url ? (
          <video key={clip.video_url} src={fileUrl(clip.video_url)} poster={fileUrl(clip.thumb_url)}
            controls preload="none" className="h-full w-full object-contain" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-zinc-500">
            {clip.render_status === "failed" ? "Falha ao renderizar" : "Renderizando…"}
          </div>
        )}
        <span className={`absolute left-2 top-2 rounded-full px-2 py-0.5 text-xs font-bold text-white ${scoreColor(clip.score)}`}
          title="Potencial viral (0–100)">
          #{rank} · {clip.score}
        </span>
        <span className="absolute right-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-[10px] text-zinc-200"
          title="Quem analisou este clipe">
          {RANKER_LABEL[clip.ranker] ?? clip.ranker}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        {editing ? (
          <>
            <input className="input" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)}
              aria-label="Título" />
            <input className="input" value={hook} maxLength={200} placeholder="Gancho (3 primeiros segundos)"
              onChange={(e) => setHook(e.target.value)} aria-label="Gancho" />
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-zinc-400">
                Início (s)
                <input className="input mt-1" type="number" step="0.1" value={start}
                  onChange={(e) => setStart(Number(e.target.value))} />
              </label>
              <label className="text-xs text-zinc-400">
                Fim (s)
                <input className="input mt-1" type="number" step="0.1" value={end}
                  onChange={(e) => setEnd(Number(e.target.value))} />
              </label>
            </div>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <div className="mt-auto flex gap-2">
              <button className="btn flex-1" disabled={busy} onClick={save}>
                {busy ? "Salvando…" : "Salvar e renderizar"}
              </button>
              <button className="btn-ghost" onClick={() => setEditing(false)}>Cancelar</button>
            </div>
          </>
        ) : (
          <>
            <h3 className="line-clamp-2 font-semibold">{clip.title || "Sem título"}</h3>
            {clip.hook && <p className="text-sm text-brand">“{clip.hook}”</p>}
            <p className="text-xs text-zinc-500">
              {fmtTime(clip.start_s)} – {fmtTime(clip.end_s)} · {Math.round(clip.end_s - clip.start_s)}s
            </p>
            <p className="line-clamp-3 text-xs text-zinc-400">{clip.reason}</p>
            <div className="mt-auto flex gap-2 pt-2">
              {clip.video_url && (
                <a className="btn flex-1" href={fileUrl(clip.video_url)} download>
                  Baixar
                </a>
              )}
              <button className="btn-ghost" onClick={() => setEditing(true)}>Editar</button>
            </div>
          </>
        )}
      </div>
    </article>
  );
}

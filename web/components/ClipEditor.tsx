"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api, Clip, fileUrl, Project } from "@/lib/api";

const fmt = (s: number) => {
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
};
const round = (v: number) => Math.round(v * 10) / 10;

type Cut = [number, number];

export default function ClipEditor({ clip, project, onClose, onSaved }: {
  clip: Clip; project: Project; onClose: () => void; onSaved: () => void;
}) {
  const duration = project.duration_s ?? clip.end_s;
  const whole = project.settings.mode === "download";
  // janela visível na linha do tempo: vídeo inteiro (só baixar) ou o clipe com folga de 30 s
  const [w0, w1] = whole ? [0, duration] : [Math.max(0, clip.start_s - 30), Math.min(duration, clip.end_s + 30)];
  const [start, setStart] = useState(clip.start_s);
  const [end, setEnd] = useState(clip.end_s);
  const [cuts, setCuts] = useState<Cut[]>((clip.cuts ?? []).map((c) => [c[0], c[1]] as Cut));
  const [title, setTitle] = useState(clip.title);
  const [hook, setHook] = useState(clip.hook);
  const [cutIn, setCutIn] = useState<number | null>(null);
  const [t, setT] = useState(clip.start_s);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  const drag = useRef<"start" | "end" | null>(null);

  const ads = useMemo(() => (project.skip_segments ?? []).filter((s) => s.end > w0 && s.start < w1), [project, w0, w1]);
  const finalDur = Math.max(0, end - start - cuts.reduce((a, [x, y]) => a + (Math.min(y, end) - Math.max(x, start)), 0));
  const pct = (v: number) => `${((v - w0) / Math.max(0.001, w1 - w0)) * 100}%`;
  const src = project.source_file_url ? fileUrl(project.source_file_url.split("&dl=")[0]) : undefined;

  useEffect(() => {
    const v = video.current;
    if (v) v.currentTime = clip.start_s;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [clip.start_s, onClose]);

  // prévia: pula os cortes e para no fim, como no vídeo final
  function onTime() {
    const v = video.current;
    if (!v) return;
    const now = v.currentTime;
    setT(now);
    if (v.paused) return;
    const inside = cuts.find(([a, b]) => now >= a && now < b - 0.05);
    if (inside) v.currentTime = inside[1];
    else if (now >= end) {
      v.pause();
      v.currentTime = end;
    } else if (now < start - 0.2) v.currentTime = start;
  }

  const seek = (v: number) => {
    if (video.current) video.current.currentTime = Math.max(0, Math.min(duration, v));
    setT(v);
  };
  const posToTime = (clientX: number) => {
    const r = bar.current!.getBoundingClientRect();
    return round(w0 + Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * (w1 - w0));
  };

  function addCut(a: number, b: number) {
    const [x, y] = [Math.max(start, Math.min(a, b)), Math.min(end, Math.max(a, b))];
    if (y - x < 0.3) return;
    const merged: Cut[] = [];
    for (const c of [...cuts, [x, y] as Cut].sort((p, q) => p[0] - q[0])) {
      const last = merged[merged.length - 1];
      if (last && c[0] <= last[1]) last[1] = Math.max(last[1], c[1]);
      else merged.push([round(c[0]), round(c[1])]);
    }
    setCuts(merged);
  }

  function markCut() {
    if (cutIn === null) setCutIn(round(t));
    else {
      addCut(cutIn, round(t));
      setCutIn(null);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const kept = cuts.filter(([a, b]) => a >= start && b <= end);
      await api(`/clips/${clip.id}`, {
        method: "PATCH",
        body: JSON.stringify({ start_s: round(start), end_s: round(end), cuts: kept, title, hook: whole ? undefined : hook }),
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar");
    } finally {
      setBusy(false);
    }
  }

  // portal: cartões de vidro (backdrop-filter) prenderiam um "position: fixed" dentro deles
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm sm:items-center sm:p-6"
      role="dialog" aria-modal="true" aria-label="Editar vídeo" onClick={onClose}>
      <div className="card ezt-rise max-h-[95vh] w-full max-w-4xl overflow-y-auto p-4 sm:p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold">Editar e cortar</h2>
          <button className="btn-ghost h-8 px-3 text-xs" onClick={onClose} aria-label="Fechar">✕</button>
        </div>

        {src ? (
          <video ref={video} src={src} controls preload="metadata" onTimeUpdate={onTime}
            className="max-h-[42vh] w-full rounded-xl bg-black" data-testid="editor-video" />
        ) : (
          <p className="text-sm text-zinc-400">O vídeo original não está disponível para prévia.</p>
        )}

        {/* linha do tempo */}
        <div className="mt-4 select-none">
          <div ref={bar} className="relative h-14 cursor-pointer overflow-hidden rounded-lg bg-zinc-800/80 ring-1 ring-white/10"
            data-testid="timeline"
            onPointerDown={(e) => { if (!drag.current) seek(posToTime(e.clientX)); }}
            onPointerMove={(e) => {
              if (!drag.current) return;
              const v = posToTime(e.clientX);
              if (drag.current === "start") setStart(Math.min(v, end - 1));
              else setEnd(Math.max(v, start + 1));
              seek(v);
            }}
            onPointerUp={() => { drag.current = null; }}>
            {ads.map((s, i) => (
              <div key={i} className="absolute inset-y-0 bg-amber-500/25"
                style={{ left: pct(s.start), width: `calc(${pct(s.end)} - ${pct(s.start)})`,
                  backgroundImage: "repeating-linear-gradient(45deg, transparent 0 6px, rgba(245,158,11,.35) 6px 12px)" }}
                title={`${s.reason} (${fmt(s.start)}–${fmt(s.end)})`} />
            ))}
            <div className="absolute inset-y-0 bg-brand/35 ring-1 ring-inset ring-violet-300/60"
              style={{ left: pct(start), width: `calc(${pct(end)} - ${pct(start)})` }} />
            {cuts.map(([a, b], i) => (
              <div key={i} className="absolute inset-y-2 rounded bg-red-500/70" style={{ left: pct(a), width: `calc(${pct(b)} - ${pct(a)})` }}
                title={`Corte ${fmt(a)}–${fmt(b)}`} />
            ))}
            {cutIn !== null && <div className="absolute inset-y-0 w-0.5 bg-red-400" style={{ left: pct(cutIn) }} />}
            <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow-[0_0_6px_white]" style={{ left: pct(t) }} />
            {(["start", "end"] as const).map((h) => (
              <div key={h} role="slider" aria-label={h === "start" ? "Início" : "Fim"}
                aria-valuenow={h === "start" ? start : end} tabIndex={0}
                className="absolute inset-y-0 z-10 w-3 -translate-x-1/2 cursor-ew-resize rounded bg-white/90 shadow"
                style={{ left: pct(h === "start" ? start : end) }}
                onPointerDown={(e) => { e.stopPropagation(); drag.current = h; bar.current?.setPointerCapture(e.pointerId); }}
                onKeyDown={(e) => {
                  const d = e.key === "ArrowLeft" ? -0.5 : e.key === "ArrowRight" ? 0.5 : 0;
                  if (!d) return;
                  if (h === "start") setStart((v) => Math.max(w0, Math.min(end - 1, round(v + d))));
                  else setEnd((v) => Math.min(w1, Math.max(start + 1, round(v + d))));
                }} />
            ))}
          </div>
          <div className="mt-1 flex justify-between font-mono text-[11px] text-zinc-500">
            <span>{fmt(w0)}</span><span>agora {fmt(t)}</span><span>{fmt(w1)}</span>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn-ghost text-xs" onClick={() => setStart(Math.min(round(t), end - 1))}>⏮ Início aqui</button>
          <button className="btn-ghost text-xs" onClick={() => setEnd(Math.max(round(t), start + 1))}>Fim aqui ⏭</button>
          <button className={cutIn === null ? "btn-ghost text-xs" : "btn text-xs"} onClick={markCut} data-testid="mark-cut">
            {cutIn === null ? "✂ Marcar corte" : `✂ Terminar corte (desde ${fmt(cutIn)})`}
          </button>
          {ads.length > 0 && (
            <button className="btn-ghost text-xs" onClick={() => ads.forEach((s) => addCut(s.start, s.end))}>
              Cortar propagandas/finais detectados ({ads.length})
            </button>
          )}
          {cuts.length > 0 && <button className="btn-ghost text-xs text-danger" onClick={() => setCuts([])}>Limpar cortes</button>}
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="text-xs text-zinc-400">Início (s)
            <input className="input mt-1" type="number" step="0.1" min={0} value={start}
              onChange={(e) => setStart(Number(e.target.value))} />
          </label>
          <label className="text-xs text-zinc-400">Fim (s)
            <input className="input mt-1" type="number" step="0.1" max={duration} value={end}
              onChange={(e) => setEnd(Number(e.target.value))} />
          </label>
          <div className="text-xs text-zinc-400">Duração final
            <p className="mt-1 rounded-xl bg-zinc-900/60 px-3 py-2 font-mono text-base text-white" data-testid="final-duration">
              {fmt(finalDur)}
            </p>
          </div>
        </div>

        {cuts.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm">
            {cuts.map(([a, b], i) => (
              <li key={i} className="flex items-center justify-between rounded-lg bg-red-500/10 px-3 py-1.5 ring-1 ring-red-400/20">
                <span>✂ Remover {fmt(a)} → {fmt(b)} <span className="text-zinc-400">({(b - a).toFixed(1)} s)</span></span>
                <button className="text-xs text-danger" onClick={() => setCuts(cuts.filter((_, j) => j !== i))}>desfazer</button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-zinc-400">Título
            <input className="input mt-1" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          {!whole && (
            <label className="text-xs text-zinc-400">Gancho (3 primeiros segundos)
              <input className="input mt-1" maxLength={200} value={hook} onChange={(e) => setHook(e.target.value)} />
            </label>
          )}
        </div>
        <p className="mt-3 text-[11px] text-zinc-500">
          Faixas listradas amarelas: propaganda, pedido de inscrição ou final de vídeo detectados. Arraste as alças brancas
          para aparar; o play da prévia já pula os cortes.
        </p>
        {error && <p className="mt-3 rounded-lg bg-red-500/15 px-3 py-2 text-sm text-danger">{error}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn" onClick={save} disabled={busy || finalDur < 1} data-testid="save-edit">
            {busy ? "Salvando…" : "Salvar e renderizar"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

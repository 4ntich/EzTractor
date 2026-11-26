"use client";

import { useState } from "react";

import ClipEditor from "@/components/ClipEditor";
import CopyCaption from "@/components/CopyCaption";
import { Clip, fileUrl, fmtTime, isBusy, Project, RANKER_LABEL } from "@/lib/api";

function scoreColor(score: number) {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 60) return "bg-amber-500";
  return "bg-zinc-600";
}

export default function ClipCard({ clip, rank, project, onChange }: {
  clip: Clip; rank: number; project: Project; onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const cutTotal = (clip.cuts ?? []).reduce((acc, [x, y]) => acc + (y - x), 0);

  return (
    <article className="card card-hover flex flex-col overflow-hidden">
      <div className="relative aspect-[9/16] bg-black">
        {clip.render_status === "ready" && clip.video_url ? (
          <video key={clip.video_url} src={fileUrl(clip.video_url)} poster={fileUrl(clip.thumb_url)}
            controls preload="none" className="h-full w-full object-contain" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-zinc-500">
            {clip.render_status === "failed" ? "Falha ao renderizar" : "Renderizando…"}
          </div>
        )}
        <span className={`absolute left-2 top-2 rounded-full px-2 py-0.5 text-xs font-bold text-onvideo ${scoreColor(clip.score)}`}
          title="Potencial viral (0–100)">
          #{rank} · {clip.score}
        </span>
        <span className="absolute right-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-[10px] text-onvideo"
          title="Quem analisou este clipe">
          {RANKER_LABEL[clip.ranker] ?? clip.ranker}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
          <>
            <h3 className="line-clamp-2 font-semibold">{clip.title || "Sem título"}</h3>
            {clip.hook && <p className="text-sm text-brand">“{clip.hook}”</p>}
            <p className="text-xs text-zinc-500">
              {fmtTime(clip.start_s)} – {fmtTime(clip.end_s)} · {Math.round(clip.end_s - clip.start_s - cutTotal)}s
              {cutTotal > 0 && <span className="ml-1 text-red-300">· {clip.cuts!.length} corte(s)</span>}
            </p>
            <p className="line-clamp-3 text-xs text-zinc-400">{clip.reason}</p>
            <div className="mt-auto pt-1"><CopyCaption clip={clip} compact /></div>
            <div className="flex gap-2">
              {clip.video_url && (
                <a className="btn flex-1" href={fileUrl(clip.download_url ?? clip.video_url)} download>
                  Baixar
                </a>
              )}
              <button className="btn-ghost" onClick={() => setEditing(true)}
                disabled={clip.render_status === "pending" || isBusy(project)}
                title={isBusy(project) ? "Aguarde o processamento terminar para editar" : "Aparar e cortar"}
                data-testid="edit-clip">✂ Editar</button>
            </div>
          </>
      </div>
      {editing && <ClipEditor clip={clip} project={project} onClose={() => setEditing(false)} onSaved={onChange} />}
    </article>
  );
}

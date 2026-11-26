import type { Project } from "@/lib/api";

const STAGES: Record<string, string> = {
  ingest: "Baixando vídeo",
  transcribe: "Transcrevendo",
  analyze: "Analisando imagem e momentos",
  banners: "Procurando banners",
  rank: "Ranqueando",
  render: "Gerando vídeo",
  done: "Pronto",
};

const pill = "rounded-full px-2.5 py-0.5 text-xs font-medium ring-1";

export default function StatusBadge({ p }: { p: Pick<Project, "status" | "stage" | "progress"> & { control?: string } }) {
  if (p.status === "ready") return <span className={`${pill} bg-emerald-500/15 text-emerald-300 ring-emerald-400/30`}>Pronto</span>;
  if (p.status === "failed") return <span className={`${pill} bg-red-500/15 text-danger ring-red-400/30`}>Falhou</span>;
  if (p.status === "cancelled") return <span className={`${pill} bg-zinc-500/15 text-zinc-300 ring-zinc-400/30`}>Cancelado</span>;
  if (p.status === "paused") {
    return <span className={`${pill} bg-sky-500/15 text-sky-300 ring-sky-400/30`}>⏸ Pausado · {p.progress}%</span>;
  }
  const waiting = p.control === "pause" ? "Pausando…" : p.control === "cancel" ? "Cancelando…" : null;
  const label = waiting ?? (p.status === "queued" ? "Na fila" : STAGES[p.stage] ?? "Processando");
  return (
    <span className={`${pill} bg-amber-500/15 text-amber-300 ring-amber-400/30`}>
      {label} · {p.progress}%
    </span>
  );
}

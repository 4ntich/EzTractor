import type { Project } from "@/lib/api";

const STAGES: Record<string, string> = {
  ingest: "Baixando vídeo",
  transcribe: "Transcrevendo",
  analyze: "Analisando momentos",
  rank: "Ranqueando com IA",
  render: "Gerando clipes",
  done: "Pronto",
};

export default function StatusBadge({ p }: { p: Pick<Project, "status" | "stage" | "progress"> }) {
  if (p.status === "ready") return <span className="rounded-full bg-emerald-950 px-2 py-0.5 text-xs text-emerald-300">Pronto</span>;
  if (p.status === "failed") return <span className="rounded-full bg-red-950 px-2 py-0.5 text-xs text-red-300">Falhou</span>;
  const label = p.status === "queued" ? "Na fila" : STAGES[p.stage] ?? "Processando";
  return (
    <span className="rounded-full bg-amber-950 px-2 py-0.5 text-xs text-amber-300">
      {label} · {p.progress}%
    </span>
  );
}

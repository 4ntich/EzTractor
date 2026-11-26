"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import NewProjectForm from "@/components/NewProjectForm";
import StatusBadge from "@/components/StatusBadge";
import { api, fmtTime, isBusy, Project } from "@/lib/api";

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[] | null>(null);

  const load = useCallback(() => {
    api<Project[]>("/projects").then(setProjects).catch(() => setProjects([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // atualiza enquanto houver algo processando
  useEffect(() => {
    if (!projects?.some((p) => isBusy(p))) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [projects, load]);

  // posição na fila (os projetos são processados um de cada vez, do mais antigo para o mais novo)
  const queuePos: Record<string, number> = {};
  (projects ?? []).filter((p) => p.status === "queued")
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .forEach((p, i) => { queuePos[p.id] = i + 1; });

  return (
    <div className="space-y-10">
      <section>
        <h1 className="mb-4 text-2xl font-bold">Novo projeto</h1>
        <NewProjectForm />
      </section>

      <section>
        <h2 className="mb-4 text-xl font-bold">Seus projetos</h2>
        {projects === null ? (
          <p className="text-sm text-zinc-500">Carregando…</p>
        ) : projects.length === 0 ? (
          <p className="text-sm text-zinc-500">Nenhum projeto ainda. Cole um link acima para começar.</p>
        ) : (
          <ul className="card divide-y divide-zinc-700/50 overflow-hidden">
            {projects.map((p) => (
              <li key={p.id}>
                <Link href={`/app/project/?id=${p.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 transition hover:bg-white/5">
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      {p.settings?.mode === "download" && <span className="mr-2 rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] text-sky-300">DOWNLOAD</span>}
                      {p.settings?.batch && <span className="mr-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">🔥 {p.settings.batch}</span>}
                      {p.title}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {new Date(p.created_at).toLocaleString("pt-BR")}
                      {p.duration_s ? ` · ${fmtTime(p.duration_s)}` : ""}
                    </p>
                  </div>
                  <span className="flex items-center gap-2">
                    {queuePos[p.id] && <span className="text-xs text-zinc-500">{queuePos[p.id] === 1 ? "próximo" : `${queuePos[p.id]}º na fila`}</span>}
                    <StatusBadge p={p} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

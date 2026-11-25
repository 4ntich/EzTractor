"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import NewProjectForm from "@/components/NewProjectForm";
import StatusBadge from "@/components/StatusBadge";
import { api, fmtTime, Project } from "@/lib/api";

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
    if (!projects?.some((p) => p.status === "queued" || p.status === "processing")) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [projects, load]);

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
          <ul className="divide-y divide-zinc-800 overflow-hidden rounded-xl border border-zinc-800">
            {projects.map((p) => (
              <li key={p.id}>
                <Link href={`/app/project/?id=${p.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-zinc-900">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{p.title}</p>
                    <p className="text-xs text-zinc-500">
                      {new Date(p.created_at).toLocaleString("pt-BR")}
                      {p.duration_s ? ` · ${fmtTime(p.duration_s)}` : ""}
                    </p>
                  </div>
                  <StatusBadge p={p} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

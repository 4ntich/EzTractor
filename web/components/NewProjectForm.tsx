"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api, Project, ProjectSettings } from "@/lib/api";

const DEFAULTS: ProjectSettings = {
  clip_min_s: 15,
  clip_max_s: 45,
  max_clips: 8,
  language: null,
  layout: "crop",
  facecam: null,
  game: "",
  captions: true,
};

const CORNERS: Record<string, { x: number; y: number }> = {
  "sup-esq": { x: 0, y: 0 },
  "sup-dir": { x: 0.72, y: 0 },
  "inf-esq": { x: 0, y: 0.7 },
  "inf-dir": { x: 0.72, y: 0.7 },
};

export default function NewProjectForm({ onCreated }: { onCreated?: () => void }) {
  const router = useRouter();
  const [source, setSource] = useState<"url" | "upload">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [s, setS] = useState<ProjectSettings>(DEFAULTS);
  const [corner, setCorner] = useState("sup-esq");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof ProjectSettings>(k: K, v: ProjectSettings[K]) => setS((prev) => ({ ...prev, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const settings: ProjectSettings = {
      ...s,
      facecam: s.layout === "split" ? { ...CORNERS[corner], w: 0.28, h: 0.3 } : null,
    };
    try {
      let project: Project;
      if (source === "url") {
        project = await api<Project>("/projects/url", {
          method: "POST",
          body: JSON.stringify({ url, title, settings }),
        });
      } else {
        if (!file) throw new Error("Escolha um arquivo de vídeo");
        const form = new FormData();
        form.append("file", file);
        form.append("title", title);
        form.append("settings", JSON.stringify(settings));
        project = await api<Project>("/projects/upload", { method: "POST", body: form });
      }
      onCreated?.();
      router.push(`/app/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-5 p-5">
      <div className="flex gap-2">
        {(["url", "upload"] as const).map((k) => (
          <button key={k} type="button" onClick={() => setSource(k)}
            className={source === k ? "btn" : "btn-ghost"}>
            {k === "url" ? "Colar link" : "Enviar arquivo"}
          </button>
        ))}
      </div>

      {source === "url" ? (
        <div>
          <label className="label" htmlFor="url">Link do VOD (Twitch, YouTube, Kick…)</label>
          <input id="url" className="input" type="url" required placeholder="https://www.twitch.tv/videos/…"
            value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
      ) : (
        <div>
          <label className="label" htmlFor="file">Arquivo de vídeo</label>
          <input id="file" type="file" required accept=".mp4,.mov,.mkv,.webm,.flv,.avi"
            className="input file:mr-3 file:rounded file:border-0 file:bg-zinc-700 file:px-3 file:py-1 file:text-zinc-100"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="title">Título (opcional)</label>
          <input id="title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="game">Jogo (ajuda a IA)</label>
          <input id="game" className="input" placeholder="Valorant, Free Fire, CS2…" value={s.game}
            onChange={(e) => set("game", e.target.value)} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <div>
          <label className="label" htmlFor="min">Duração mín. (s)</label>
          <input id="min" type="number" min={5} max={180} className="input" value={s.clip_min_s}
            onChange={(e) => set("clip_min_s", Number(e.target.value))} />
        </div>
        <div>
          <label className="label" htmlFor="max">Duração máx. (s)</label>
          <input id="max" type="number" min={5} max={180} className="input" value={s.clip_max_s}
            onChange={(e) => set("clip_max_s", Number(e.target.value))} />
        </div>
        <div>
          <label className="label" htmlFor="n">Nº de clipes</label>
          <input id="n" type="number" min={1} max={30} className="input" value={s.max_clips}
            onChange={(e) => set("max_clips", Number(e.target.value))} />
        </div>
        <div>
          <label className="label" htmlFor="lang">Idioma</label>
          <select id="lang" className="input" value={s.language ?? ""}
            onChange={(e) => set("language", e.target.value || null)}>
            <option value="">Detectar</option>
            <option value="pt">Português</option>
            <option value="en">Inglês</option>
            <option value="es">Espanhol</option>
          </select>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label className="label" htmlFor="layout">Layout vertical</label>
          <select id="layout" className="input" value={s.layout}
            onChange={(e) => set("layout", e.target.value as ProjectSettings["layout"])}>
            <option value="crop">Recorte central</option>
            <option value="fit">Vídeo inteiro + fundo desfocado</option>
            <option value="split">Webcam em cima + jogo embaixo</option>
          </select>
        </div>
        {s.layout === "split" && (
          <div>
            <label className="label" htmlFor="corner">Posição da webcam</label>
            <select id="corner" className="input" value={corner} onChange={(e) => setCorner(e.target.value)}>
              <option value="sup-esq">Superior esquerda</option>
              <option value="sup-dir">Superior direita</option>
              <option value="inf-esq">Inferior esquerda</option>
              <option value="inf-dir">Inferior direita</option>
            </select>
          </div>
        )}
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input type="checkbox" checked={s.captions} onChange={(e) => set("captions", e.target.checked)} />
          Legendas automáticas
        </label>
      </div>

      {error && <p className="rounded-lg bg-red-950 px-3 py-2 text-sm text-red-300">{error}</p>}
      <button className="btn w-full sm:w-auto" disabled={busy}>
        {busy ? (source === "upload" ? "Enviando…" : "Criando…") : "Gerar clipes"}
      </button>
    </form>
  );
}

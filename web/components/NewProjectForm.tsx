"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api, Capabilities, DOWNLOAD_QUALITIES, Project, ProjectSettings, Ranker, RENDER_QUALITIES } from "@/lib/api";
import type { Template } from "@/lib/templates";

const DEFAULTS: ProjectSettings = {
  clip_min_s: 15,
  clip_max_s: 45,
  max_clips: 8,
  language: null,
  layout: "crop",
  facecam: null,
  game: "",
  captions: true,
  ranker: null,
};

function rankerHint(r: Ranker, caps: Capabilities | null): string {
  if (r === "heuristic") return "Grátis. Nota pelos sinais; título e gancho tirados da própria fala.";
  if (r === "ollama") {
    if (!caps) return "";
    if (!caps.ollama.online) return "⚠ Ollama não está rodando. Sem ele, o app usa \"Sinais\".";
    if (!caps.ollama.model_ready) return `⚠ Modelo não baixado. Rode: ollama pull ${caps.ollama.model}`;
    return `Grátis, IA no seu computador (${caps.ollama.model}). Mais lento.`;
  }
  if (caps && !caps.claude_configured) return "⚠ ANTHROPIC_API_KEY não configurada. Sem ela, o app usa \"Sinais\".";
  return "Pago (API da Anthropic). Melhor qualidade de notas, títulos e ganchos.";
}

const CORNERS: Record<string, { x: number; y: number }> = {
  "sup-esq": { x: 0, y: 0 },
  "sup-dir": { x: 0.72, y: 0 },
  "inf-esq": { x: 0, y: 0.7 },
  "inf-dir": { x: 0.72, y: 0.7 },
};

export default function NewProjectForm() {
  const router = useRouter();
  const [source, setSource] = useState<"url" | "upload">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [s, setS] = useState<ProjectSettings>(DEFAULTS);
  const [corner, setCorner] = useState("sup-esq");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [ranker, setRanker] = useState<Ranker>("heuristic");
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateId, setTemplateId] = useState<string>("");
  const userPicked = useRef(false); // não sobrescrever a escolha do usuário com o padrão do servidor
  const [mode, setMode] = useState<"clips" | "download">("clips");
  const [renderHeight, setRenderHeight] = useState(1920);
  const [downloadHeight, setDownloadHeight] = useState(1080);
  const qualityPicked = useRef(false);

  useEffect(() => {
    api<Template[]>("/templates")
      .then((ts) => {
        setTemplates(ts);
        setTemplateId(ts.find((t) => t.is_default)?.id ?? "");
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    api<Capabilities>("/capabilities")
      .then((c) => {
        setCaps(c);
        if (!userPicked.current) setRanker(c.default_ranker);
        if (!qualityPicked.current && RENDER_QUALITIES.some((q) => q.value === c.default_render_height)) {
          setRenderHeight(c.default_render_height);
        }
      })
      .catch(() => {});
  }, []);

  const set = <K extends keyof ProjectSettings>(k: K, v: ProjectSettings[K]) => setS((prev) => ({ ...prev, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const settings: ProjectSettings = {
      ...s,
      ranker,
      template_id: templateId || null,
      mode,
      download_height: downloadHeight,
      render_height: renderHeight,
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
      router.push(`/app/project/?id=${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-5 p-5">
      <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="O que fazer">
        {([
          ["clips", "✂️  Gerar cortes com IA", "Encontra os melhores momentos e cria clipes verticais."],
          ["download", "⬇️  Só baixar o vídeo", "Baixa o vídeo inteiro, com ou sem template aplicado."],
        ] as const).map(([k, t, d]) => (
          <button key={k} type="button" role="radio" aria-checked={mode === k} onClick={() => setMode(k)}
            data-testid={`mode-${k}`}
            className={`rounded-xl border p-3 text-left transition ${mode === k
              ? "border-violet-400 bg-violet-500/15 shadow-glow" : "border-zinc-700/70 hover:bg-white/5"}`}>
            <span className="block font-semibold text-white">{t}</span>
            <span className="mt-0.5 block text-xs text-zinc-400">{d}</span>
          </button>
        ))}
      </div>

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
          <label className="label" htmlFor="game">{mode === "clips" ? "Jogo (ajuda a IA)" : "Jogo (usado no {jogo} do template)"}</label>
          <input id="game" className="input" placeholder="Valorant, Free Fire, CS2…" value={s.game}
            onChange={(e) => set("game", e.target.value)} />
        </div>
      </div>

      {mode === "clips" && (
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
      )}

      <div>
        <label className="label" htmlFor="template">Template (textos, fontes e molduras)</label>
        <div className="flex gap-2">
          <select id="template" className="input" value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            <option value="">{mode === "download" ? "Sem template (vídeo original)" : "Sem template (estilo simples)"}</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.name}{t.is_default ? " (padrão)" : ""}</option>
            ))}
          </select>
          <Link href="/app/templates" className="btn-ghost shrink-0 text-xs">Criar / editar</Link>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {source === "url" && (
          <div>
            <label className="label" htmlFor="dl-quality">Qualidade do download</label>
            <select id="dl-quality" className="input" value={downloadHeight}
              onChange={(e) => setDownloadHeight(Number(e.target.value))}>
              {DOWNLOAD_QUALITIES.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}
            </select>
          </div>
        )}
        {(mode === "clips" || templateId) && (
          <div>
            <label className="label" htmlFor="quality">Qualidade do vídeo final</label>
            <select id="quality" className="input" value={renderHeight}
              onChange={(e) => { qualityPicked.current = true; setRenderHeight(Number(e.target.value)); }}>
              {RENDER_QUALITIES.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}
            </select>
          </div>
        )}
      </div>
      {(mode === "clips" || templateId) && renderHeight > 1920 && (
        <p className="-mt-2 text-xs text-amber-300">
          Acima de 1080p a renderização fica bem mais lenta e os arquivos maiores. Só vale se o vídeo original tiver essa qualidade.
        </p>
      )}
      {mode === "download" && !templateId && (
        <p className="-mt-2 text-xs text-zinc-400">
          Sem template, o vídeo é baixado como está (sem cortes nem conversão). Escolha um template para aplicar textos, moldura e formato.
        </p>
      )}

      {mode === "clips" && (
      <div>
        <span className="label">Método de análise</span>
        <div className="grid gap-2 sm:grid-cols-3">
          {(["heuristic", "ollama", "claude"] as const).map((r) => (
            <button key={r} type="button" onClick={() => { userPicked.current = true; setRanker(r); }}
              className={`rounded-lg border px-3 py-2 text-left text-sm transition ${
                ranker === r ? "border-brand bg-brand/10" : "border-zinc-700 hover:bg-zinc-800"}`}>
              <b>{r === "heuristic" ? "Sinais" : r === "ollama" ? "IA local (Ollama)" : "Claude"}</b>
              <span className="ml-2 text-xs text-zinc-400">{r === "claude" ? "pago" : "grátis"}</span>
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-zinc-400">{rankerHint(ranker, caps)}</p>
      </div>
      )}

      {(mode === "clips" || templateId) && (
      <div className="grid gap-4 sm:grid-cols-3">
        {mode === "clips" && (
        <div>
          <label className="label" htmlFor="layout">Layout vertical</label>
          <select id="layout" className="input" value={s.layout}
            onChange={(e) => set("layout", e.target.value as ProjectSettings["layout"])}>
            <option value="crop">Recorte central</option>
            <option value="fit">Vídeo inteiro + fundo desfocado</option>
            <option value="split">Webcam em cima + jogo embaixo</option>
          </select>
        </div>
        )}
        {mode === "clips" && s.layout === "split" && (
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
      )}

      {error && <p className="rounded-lg bg-red-500/15 px-3 py-2 text-sm text-danger ring-1 ring-red-400/30">{error}</p>}
      <button className="btn w-full sm:w-auto" disabled={busy}>
        {busy ? (source === "upload" ? "Enviando…" : "Criando…")
          : mode === "clips" ? "Gerar clipes" : templateId ? "Baixar e aplicar template" : "Baixar vídeo"}
      </button>
    </form>
  );
}

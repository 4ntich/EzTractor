"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import TemplateCanvas, { SafeArea } from "@/components/TemplateCanvas";
import { Choice, Color, Group, Range, Swatch, Tabs, Toggle } from "@/components/ui";
import { api, API_URL, getToken, Project } from "@/lib/api";
import {
  ANIMATIONS, ASPECTS, blankConfig, CaptionStyle, defaultLayer, Edge, EdgeKey, EDGES, Frame, Layer, LayerKind,
  MAX_LAYERS, newId, Preset, ProgressBar, Template, TemplateConfig, TemplateOptions,
} from "@/lib/templates";

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

type Panel = "textos" | "bordas" | "video" | "legendas" | "extras";
type View = "editar" | "real";

// estilos rápidos de borda: quais lados ligar e com que tamanho
const BORDER_STYLES: { key: string; label: string; edges: Partial<Record<EdgeKey, number>> }[] = [
  { key: "none", label: "Nenhuma", edges: {} },
  { key: "tarjas", label: "Tarjas", edges: { top: 12, bottom: 12 } },
  { key: "topo", label: "Só topo", edges: { top: 10 } },
  { key: "laterais", label: "Laterais", edges: { left: 3, right: 3 } },
  { key: "moldura", label: "Moldura completa", edges: { top: 3, bottom: 3, left: 3, right: 3 } },
];

export default function TemplatesPage() {
  const [opts, setOpts] = useState<TemplateOptions | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [library, setLibrary] = useState<Template[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [tab, setTab] = useState<"galeria" | "biblioteca">("galeria");
  const [category, setCategory] = useState("Todos");

  const [cfg, setCfg] = useState<TemplateConfig>(blankConfig());
  const [selectedId, setSelectedId] = useState<string | null>(cfg.layers[0]?.id ?? null);
  const [name, setName] = useState("Meu template");
  const [isDefault, setIsDefault] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [animKey, setAnimKey] = useState(0);
  const [panel, setPanel] = useState<Panel>("textos");

  // palco único: edição ao vivo ou render real (mesmo motor do vídeo final), no mesmo quadro
  const [view, setView] = useState<View>("editar");
  const [showSampleCap, setShowSampleCap] = useState(true);
  const [safeMode, setSafeMode] = useState<SafeArea>("normal");
  useEffect(() => {
    try {
      const v = localStorage.getItem("ezt-safe-area");
      if (v === "normal" || v === "tiktok" || v === "off") setSafeMode(v);
    } catch { /* armazenamento indisponível: fica o padrão */ }
  }, []);
  const changeSafeMode = (v: SafeArea) => {
    setSafeMode(v);
    try { localStorage.setItem("ezt-safe-area", v); } catch { /* ignora */ }
  };
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewProject, setPreviewProject] = useState("");
  const seq = useRef(0);

  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const families = useMemo(
    () => Object.fromEntries((opts?.fonts ?? []).map((f) => [f.key, f.family])),
    [opts],
  );
  const fontGroups = useMemo(() => {
    const g: Record<string, { key: string; label: string; family: string }[]> = {};
    for (const f of opts?.fonts ?? []) (g[f.group] ??= []).push(f);
    return g;
  }, [opts]);

  const loadLibrary = useCallback(() => api<Template[]>("/templates").then(setLibrary).catch(() => {}), []);

  useEffect(() => {
    api<TemplateOptions>("/template-options").then(setOpts).catch(() => {});
    api<Preset[]>("/template-presets").then(setPresets).catch(() => {});
    api<Project[]>("/projects").then((ps) => setProjects(ps.filter((p) => p.status === "ready"))).catch(() => {});
    loadLibrary();
  }, [loadLibrary]);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 3500);
    return () => clearTimeout(t);
  }, [notice]);

  // ------------------------------------------------------------ edição
  const update = (patch: Partial<TemplateConfig>) => {
    setCfg((c) => ({ ...c, ...patch }));
    setDirty(true);
  };
  const updateFrame = (patch: Partial<Frame>) => {
    setCfg((c) => ({ ...c, frame: { ...c.frame, ...patch } }));
    setDirty(true);
  };
  const updateEdge = (k: EdgeKey, patch: Partial<Edge>) => {
    setCfg((c) => ({ ...c, frame: { ...c.frame, [k]: { ...c.frame[k], ...patch } } }));
    setDirty(true);
  };
  const updateCaps = (patch: Partial<CaptionStyle>) => update({ captions: { ...cfg.captions, ...patch } });
  const updateBar = (patch: Partial<ProgressBar>) => update({ progressBar: { ...cfg.progressBar, ...patch } });
  const updateLayer = (id: string, patch: Partial<Layer>) => {
    setCfg((c) => ({ ...c, layers: c.layers.map((l) => (l.id === id ? { ...l, ...patch } : l)) }));
    setDirty(true);
  };
  const sel = cfg.layers.find((l) => l.id === selectedId) ?? null;

  function load(config: TemplateConfig, o: { name: string; id?: string | null; isDefault?: boolean }) {
    const c = clone(config);
    setCfg(c);
    setSelectedId(c.layers[0]?.id ?? null);
    setName(o.name);
    setEditingId(o.id ?? null);
    setIsDefault(Boolean(o.isDefault));
    setDirty(false);
    setPreviewUrl(null);
    setAnimKey((k) => k + 1);
    window.scrollTo({ top: document.getElementById("editor")?.offsetTop ?? 0, behavior: "smooth" });
  }

  function addLayer(kind: LayerKind) {
    if (cfg.layers.length >= MAX_LAYERS) return;
    const l = defaultLayer(kind, cfg.accentColor);
    update({ layers: [...cfg.layers, l] });
    setSelectedId(l.id);
  }
  function duplicateLayer(l: Layer) {
    if (cfg.layers.length >= MAX_LAYERS) return;
    const copy = { ...clone(l), id: newId(), y: Math.min(96, l.y + 5) };
    update({ layers: [...cfg.layers, copy] });
    setSelectedId(copy.id);
  }
  function removeLayer(id: string) {
    const rest = cfg.layers.filter((l) => l.id !== id);
    update({ layers: rest });
    setSelectedId(rest[0]?.id ?? null);
  }
  function moveLayer(id: string, dir: -1 | 1) {
    const i = cfg.layers.findIndex((l) => l.id === id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= cfg.layers.length) return;
    const ls = [...cfg.layers];
    [ls[i], ls[j]] = [ls[j], ls[i]];
    update({ layers: ls });
  }
  function distribute() {
    const n = cfg.layers.length;
    if (!n) return;
    update({
      layers: cfg.layers.map((l, i) => ({ ...l, x: 50, align: "center", y: n === 1 ? 50 : 12 + (i * 76) / (n - 1) })),
    });
  }
  function insertVar(v: string) {
    if (!sel) return;
    updateLayer(sel.id, { text: `${sel.text}${sel.text && !sel.text.endsWith(" ") ? " " : ""}{${v}}` });
  }
  function applyBorderStyle(edges: Partial<Record<EdgeKey, number>>) {
    setCfg((c) => {
      const f = { ...c.frame };
      for (const { key } of EDGES) {
        const size = edges[key];
        f[key] = size ? { ...f[key], enabled: true, size } : { ...f[key], enabled: false };
      }
      return { ...c, frame: f };
    });
    setDirty(true);
  }
  function colorAllEdges(color: string) {
    setCfg((c) => ({
      ...c,
      frame: { ...c.frame, top: { ...c.frame.top, color }, bottom: { ...c.frame.bottom, color },
        left: { ...c.frame.left, color }, right: { ...c.frame.right, color } },
    }));
    setDirty(true);
  }

  // ------------------------------------------------------------ render real (atualiza sozinho)
  const renderReal = useCallback(async () => {
    const my = ++seq.current;
    setPreviewBusy(true);
    setPreviewError(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const tok = getToken();
      if (tok) headers.Authorization = `Bearer ${tok}`;
      const res = await fetch(`${API_URL}/templates/preview`, {
        method: "POST", headers,
        body: JSON.stringify({ config: cfg, project_id: previewProject || null, captions: showSampleCap }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? "Falha na prévia");
      const blob = await res.blob();
      if (my !== seq.current) return; // chegou uma versão mais nova no meio do caminho
      setPreviewUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return URL.createObjectURL(blob);
      });
    } catch (e) {
      if (my === seq.current) setPreviewError(e instanceof Error ? e.message : "Falha na prévia");
    } finally {
      if (my === seq.current) setPreviewBusy(false);
    }
  }, [cfg, previewProject, showSampleCap]);

  useEffect(() => {
    if (view !== "real") return;
    const t = setTimeout(renderReal, 450);
    return () => clearTimeout(t);
  }, [view, renderReal]);

  // ------------------------------------------------------------ servidor
  async function save(asNew: boolean) {
    const body = JSON.stringify({ name: name.trim(), config: cfg, is_default: isDefault });
    try {
      const t = asNew || !editingId
        ? await api<Template>("/templates", { method: "POST", body })
        : await api<Template>(`/templates/${editingId}`, { method: "PUT", body });
      setEditingId(t.id);
      setDirty(false);
      setNotice({ ok: true, text: asNew || !editingId ? "Template salvo na biblioteca." : "Template atualizado." });
      loadLibrary();
      setTab("biblioteca");
    } catch (e) {
      setNotice({ ok: false, text: e instanceof Error ? e.message : "Erro ao salvar" });
    }
  }

  async function saveFromPreset(p: Preset) {
    await api<Template>("/templates", { method: "POST", body: JSON.stringify({ name: p.name, config: p.config }) });
    setNotice({ ok: true, text: `“${p.name}” adicionado à biblioteca.` });
    loadLibrary();
  }

  async function setDefault(t: Template, value: boolean) {
    await api(`/templates/${t.id}`, { method: "PUT", body: JSON.stringify({ name: t.name, config: t.config, is_default: value }) });
    if (t.id === editingId) setIsDefault(value);
    loadLibrary();
  }

  async function remove(t: Template) {
    await api(`/templates/${t.id}`, { method: "DELETE" });
    if (t.id === editingId) setEditingId(null);
    setConfirmDelete(null);
    setNotice({ ok: true, text: "Template excluído." });
    loadLibrary();
  }

  const categories = ["Todos", ...Array.from(new Set(presets.map((p) => p.category)))];
  const shownPresets = category === "Todos" ? presets : presets.filter((p) => p.category === category);
  const vertical = cfg.width < cfg.height;
  const anyEdge = EDGES.some(({ key }) => cfg.frame[key]?.enabled);

  // ------------------------------------------------------------ UI
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Templates</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Textos, fontes, bordas e legendas aplicados automaticamente em todos os clipes. Use{" "}
            <code className="text-[rgb(var(--a-300))]">{"{titulo}"}</code> e{" "}
            <code className="text-[rgb(var(--a-300))]">{"{gancho}"}</code> para cada clipe receber o seu próprio texto.
          </p>
        </div>
        <button className="btn-ghost" onClick={() => load(blankConfig(), { name: "Meu template" })}>+ Novo em branco</button>
      </header>

      {notice && (
        <p role="status" className={`rounded-lg px-4 py-2 text-sm ${notice.ok ? "bg-emerald-950 text-emerald-300" : "bg-red-950 text-red-300"}`}>
          {notice.text}
        </p>
      )}

      {/* ------------------------------------------------ galeria / biblioteca */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Choice value={tab} onChange={setTab}
            options={[{ value: "galeria", label: `Estilos prontos (${presets.length})` }, { value: "biblioteca", label: `Meus templates (${library.length})` }]} />
          {tab === "galeria" && (
            <div className="ml-auto">
              <Choice value={category} onChange={setCategory} options={categories.map((c) => ({ value: c, label: c }))} />
            </div>
          )}
        </div>

        {tab === "galeria" ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {shownPresets.map((p) => (
              <article key={p.key} className="card card-hover flex flex-col overflow-hidden" data-testid={`preset-${p.key}`}>
                <button type="button" onClick={() => load(p.config, { name: p.name })} title="Editar este estilo"
                  className="block bg-black">
                  <div className="mx-auto" style={{ width: p.config.width >= p.config.height ? "100%" : "62%" }}>
                    <TemplateCanvas cfg={p.config} families={families} />
                  </div>
                </button>
                <div className="flex flex-1 flex-col gap-1 p-2">
                  <h3 className="text-sm font-semibold leading-tight">{p.name}</h3>
                  <p className="line-clamp-2 text-[11px] text-zinc-400">{p.description}</p>
                  <div className="mt-auto flex gap-1 pt-1">
                    <button className="btn flex-1 px-2 py-1 text-xs" onClick={() => load(p.config, { name: p.name })}>Editar</button>
                    <button className="btn-ghost px-2 py-1 text-xs" onClick={() => saveFromPreset(p)} title="Salvar na biblioteca">+ Salvar</button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : library.length === 0 ? (
          <p className="text-sm text-zinc-500">Você ainda não salvou nenhum template. Escolha um estilo pronto ou crie um em branco.</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {library.map((t) => (
              <article key={t.id} className={`card card-hover flex flex-col overflow-hidden ${t.id === editingId ? "ring-2 ring-[rgb(var(--a-400))]" : ""}`}>
                <button type="button" className="block bg-black" onClick={() => load(t.config, { name: t.name, id: t.id, isDefault: t.is_default })}>
                  <div className="mx-auto" style={{ width: t.config.width >= t.config.height ? "100%" : "62%" }}>
                    <TemplateCanvas cfg={t.config} families={families} />
                  </div>
                </button>
                <div className="flex flex-1 flex-col gap-1 p-2">
                  <h3 className="flex items-center gap-1 text-sm font-semibold leading-tight">
                    {t.is_default && <span className="rounded bg-amber-500/20 px-1 text-[10px] text-amber-300">PADRÃO</span>}
                    <span className="truncate">{t.name}</span>
                  </h3>
                  <div className="mt-auto flex flex-wrap gap-1 pt-1">
                    <button className="btn flex-1 px-2 py-1 text-xs" onClick={() => load(t.config, { name: t.name, id: t.id, isDefault: t.is_default })}>Editar</button>
                    <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setDefault(t, !t.is_default)}
                      title={t.is_default ? "Deixar de ser o padrão" : "Usar automaticamente em todos os projetos novos"}>
                      {t.is_default ? "★" : "☆"}
                    </button>
                    {confirmDelete === t.id ? (
                      <>
                        <button className="btn-ghost px-2 py-1 text-xs text-danger" onClick={() => remove(t)}>Excluir?</button>
                        <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setConfirmDelete(null)}>Não</button>
                      </>
                    ) : (
                      <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setConfirmDelete(t.id)} title="Excluir">🗑</button>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* ------------------------------------------------ editor */}
      <section id="editor" className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)]">
        {/* palco único */}
        <div className="lg:sticky lg:top-20 lg:self-start">
          <div className="card space-y-3 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Choice value={view} onChange={setView}
                options={[{ value: "editar", label: "✏️ Editar" }, { value: "real", label: "🎬 Como vai ficar" }]} />
              {dirty && <span className="text-[11px] text-amber-400">• não salvo</span>}
            </div>

            <div className="relative mx-auto overflow-hidden rounded-xl bg-black ring-1 ring-white/10"
              style={{ maxWidth: vertical ? 340 : "100%" }} data-testid="stage">
              {view === "editar" ? (
                <TemplateCanvas cfg={cfg} families={families} selectedId={selectedId} onSelect={setSelectedId}
                  onMove={(id, x, y) => updateLayer(id, { x, y })} animateKey={animKey}
                  showCaptions={showSampleCap} safeArea={safeMode} />
              ) : (
                <div className="relative w-full" style={{ aspectRatio: `${cfg.width} / ${cfg.height}` }}>
                  {previewUrl && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={previewUrl} alt="Como o vídeo final vai ficar" data-testid="real-preview"
                      className={`absolute inset-0 h-full w-full object-contain transition ${previewBusy ? "opacity-60" : ""}`} />
                  )}
                  {previewBusy && (
                    <div className="absolute inset-0 grid place-items-center">
                      <span className="rounded-lg bg-black/70 px-3 py-1.5 text-xs text-zinc-200">Renderizando…</span>
                    </div>
                  )}
                  {previewError && !previewBusy && (
                    <div className="absolute inset-x-3 bottom-3 rounded-lg bg-red-950/90 px-3 py-2 text-xs text-red-200">
                      {previewError}{" "}
                      <button className="underline" onClick={renderReal}>Tentar de novo</button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {view === "editar" ? (
              <>
                <div className="flex flex-wrap gap-2">
                  <button className="btn-ghost h-8 px-3 text-xs" onClick={() => setAnimKey((k) => k + 1)}>▶ Animações</button>
                  <button className="btn-ghost h-8 px-3 text-xs" onClick={distribute}>Centralizar textos</button>
                </div>
                <Toggle label="Legenda de exemplo" checked={showSampleCap} onChange={setShowSampleCap} />
                <div className="flex flex-wrap items-center justify-between gap-2" data-testid="safe-mode">
                  <span className="text-xs text-zinc-300">Área segura</span>
                  <Choice value={safeMode} onChange={changeSafeMode}
                    options={[{ value: "normal", label: "Normal" }, { value: "tiktok", label: "TikTok/Reels" }, { value: "off", label: "Desligada" }]} />
                </div>
                <p className="text-[11px] leading-relaxed text-zinc-500">
                  Arraste os textos na tela.{" "}
                  {safeMode === "tiktok"
                    ? "O tracejado mostra onde os botões e a legenda do TikTok/Reels não cobrem (direita e embaixo ficam ocupados)."
                    : safeMode === "normal" ? "O tracejado é uma margem igual em todos os lados." : ""}
                </p>
              </>
            ) : (
              <>
                <div className="flex gap-2">
                  <select className="input h-9 py-1 text-xs" value={previewProject} onChange={(e) => setPreviewProject(e.target.value)}
                    aria-label="Fundo da prévia">
                    <option value="">Fundo de exemplo</option>
                    {projects.map((p) => <option key={p.id} value={p.id}>Vídeo: {p.title}</option>)}
                  </select>
                  <button className="btn-ghost h-9 shrink-0 px-3 text-xs" onClick={renderReal} disabled={previewBusy} title="Renderizar de novo">↻</button>
                </div>
                <Toggle label="Legenda de exemplo" checked={showSampleCap} onChange={setShowSampleCap} />
                <p className="text-[11px] leading-relaxed text-zinc-500">
                  Mesmo motor do vídeo final. Atualiza sozinho quando você muda algo no painel ao lado.
                </p>
              </>
            )}
          </div>
        </div>

        {/* painel */}
        <div className="space-y-4">
          <div className="card flex flex-wrap items-end gap-3 p-4">
            <div className="min-w-[180px] flex-1">
              <label className="label" htmlFor="tpl-name">{editingId ? "Editando" : "Novo template"}</label>
              <input id="tpl-name" className="input" maxLength={60} value={name}
                onChange={(e) => { setName(e.target.value); setDirty(true); }} />
            </div>
            <div className="pb-2">
              <Toggle label="Padrão em projetos novos" checked={isDefault} onChange={(v) => { setIsDefault(v); setDirty(true); }} />
            </div>
            <div className="flex gap-2">
              {editingId && <button className="btn" onClick={() => save(false)} disabled={!name.trim()}>Salvar</button>}
              <button className={editingId ? "btn-ghost" : "btn"} onClick={() => save(true)} disabled={!name.trim()}>
                {editingId ? "Salvar como novo" : "Salvar na biblioteca"}
              </button>
            </div>
          </div>

          <Tabs value={panel} onChange={setPanel} tabs={[
            { value: "textos", label: "Textos", icon: "🔤" },
            { value: "bordas", label: "Bordas", icon: "🖼" },
            { value: "video", label: "Vídeo", icon: "🎞" },
            { value: "legendas", label: "Legendas", icon: "💬" },
            { value: "extras", label: "Extras", icon: "✨" },
          ]} />

          <div className="card space-y-4 p-4">
            {/* ---------------------------------------------- textos */}
            {panel === "textos" && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="label mb-0 mr-auto">Textos ({cfg.layers.length}/{MAX_LAYERS})</span>
                  <button className="btn-ghost h-8 px-3 text-xs" onClick={() => addLayer("title")} disabled={cfg.layers.length >= MAX_LAYERS}>+ Título</button>
                  <button className="btn-ghost h-8 px-3 text-xs" onClick={() => addLayer("text")} disabled={cfg.layers.length >= MAX_LAYERS}>+ Texto</button>
                  <button className="btn-ghost h-8 px-3 text-xs" onClick={() => addLayer("tag")} disabled={cfg.layers.length >= MAX_LAYERS}>+ Etiqueta</button>
                </div>
                {cfg.layers.length === 0 ? (
                  <p className="text-xs text-zinc-500">Nenhum texto. Adicione um título, texto ou etiqueta acima.</p>
                ) : (
                  <ul className="space-y-1">
                    {cfg.layers.map((l, i) => (
                      <li key={l.id} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ring-1 transition ${
                        l.id === selectedId ? "bg-[rgb(var(--a-500)/.15)] ring-[rgb(var(--a-400)/.5)]" : "ring-white/5 hover:bg-white/5"}`}>
                        <button className="min-w-0 flex-1 truncate text-left" onClick={() => setSelectedId(l.id)}>
                          <span className="mr-2 text-[10px] uppercase text-zinc-500">{l.kind === "title" ? "Título" : l.kind === "tag" ? "Etiqueta" : "Texto"}</span>
                          {l.text || <em className="text-zinc-500">vazio</em>}
                        </button>
                        <button className="text-zinc-500 hover:text-white disabled:opacity-30" onClick={() => moveLayer(l.id, -1)} disabled={i === 0} title="Para trás">↑</button>
                        <button className="text-zinc-500 hover:text-white disabled:opacity-30" onClick={() => moveLayer(l.id, 1)} disabled={i === cfg.layers.length - 1} title="Para frente">↓</button>
                        <button className="text-xs text-zinc-400 hover:text-white" onClick={() => duplicateLayer(l)} title="Duplicar">⧉</button>
                        <button className="text-xs text-danger hover:opacity-80" onClick={() => removeLayer(l.id)} title="Remover">✕</button>
                      </li>
                    ))}
                  </ul>
                )}

                {sel && (
                  <div className="space-y-3">
                    <Group title="Conteúdo">
                      <textarea className="input min-h-[60px] font-mono" maxLength={300} value={sel.text} aria-label="Texto"
                        onChange={(e) => updateLayer(sel.id, { text: e.target.value })} />
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(opts?.variables ?? {}).map(([k, desc]) => (
                          <button key={k} type="button" title={desc} onClick={() => insertVar(k)}
                            className="rounded-md bg-[rgb(var(--a-500)/.15)] px-2 py-0.5 font-mono text-[11px] text-[rgb(var(--a-200))] hover:bg-[rgb(var(--a-500)/.3)]">
                            {`{${k}}`}
                          </button>
                        ))}
                      </div>
                    </Group>

                    <Group title="Fonte">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <select className="input" value={sel.fontFamily} aria-label="Fonte"
                          onChange={(e) => updateLayer(sel.id, { fontFamily: e.target.value })}
                          style={{ fontFamily: `"${families[sel.fontFamily]}"` }}>
                          {Object.entries(fontGroups).map(([g, fs]) => (
                            <optgroup key={g} label={g}>
                              {fs.map((f) => <option key={f.key} value={f.key} style={{ fontFamily: `"${f.family}"` }}>{f.label}</option>)}
                            </optgroup>
                          ))}
                        </select>
                        <div className="flex items-center gap-3">
                          <Swatch label="Cor do texto" value={sel.color} onChange={(v) => updateLayer(sel.id, { color: v })} />
                          <Choice value={sel.align} onChange={(v) => updateLayer(sel.id, { align: v })}
                            options={[{ value: "left", label: "Esq." }, { value: "center", label: "Centro" }, { value: "right", label: "Dir." }]} />
                        </div>
                        <Range label="Tamanho" value={sel.fontSize} min={10} max={200} onChange={(v) => updateLayer(sel.id, { fontSize: v })} suffix="px" />
                        <Range label="Espaçamento" value={sel.letterSpacing} min={-10} max={60} onChange={(v) => updateLayer(sel.id, { letterSpacing: v })} suffix="px" />
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <Toggle label="Negrito" checked={sel.bold} onChange={(v) => updateLayer(sel.id, { bold: v })} />
                        <Toggle label="Itálico" checked={sel.italic} onChange={(v) => updateLayer(sel.id, { italic: v })} />
                        <Toggle label="MAIÚSC." checked={sel.uppercase} onChange={(v) => updateLayer(sel.id, { uppercase: v })} />
                      </div>
                    </Group>

                    <Group title="Posição">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <Range label="Horizontal" value={sel.x} min={0} max={100} step={0.5} onChange={(v) => updateLayer(sel.id, { x: v })} suffix="%" />
                        <Range label="Vertical" value={sel.y} min={0} max={100} step={0.5} onChange={(v) => updateLayer(sel.id, { y: v })} suffix="%" />
                        <Range label="Largura máxima" value={sel.boxWidth} min={10} max={100} onChange={(v) => updateLayer(sel.id, { boxWidth: v })} suffix="%" />
                        <Range label="Inclinação" value={sel.rotation} min={-45} max={45} onChange={(v) => updateLayer(sel.id, { rotation: v })} suffix="°" />
                      </div>
                    </Group>

                    <Group title="Efeitos">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="flex items-end gap-3">
                          <div className="flex-1"><Range label="Contorno" value={sel.outlineWidth} min={0} max={30} step={0.5} onChange={(v) => updateLayer(sel.id, { outlineWidth: v })} suffix="px" /></div>
                          <Swatch label="Cor do contorno / brilho" value={sel.outlineColor} onChange={(v) => updateLayer(sel.id, { outlineColor: v })} />
                        </div>
                        <div className="flex items-end gap-3">
                          <div className="flex-1"><Range label="Sombra" value={sel.shadowDepth} min={0} max={30} step={0.5} onChange={(v) => updateLayer(sel.id, { shadowDepth: v })} suffix="px" /></div>
                          <Swatch label="Cor da sombra" value={sel.shadowColor} onChange={(v) => updateLayer(sel.id, { shadowColor: v })} />
                        </div>
                        <Range label="Opacidade do texto" value={sel.opacity} min={0} max={100} onChange={(v) => updateLayer(sel.id, { opacity: v })} suffix="%" />
                        <Range label="Opacidade da sombra" value={sel.shadowOpacity} min={0} max={100} onChange={(v) => updateLayer(sel.id, { shadowOpacity: v })} suffix="%" />
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <Toggle label="Brilho neon" checked={sel.glow} onChange={(v) => updateLayer(sel.id, { glow: v })} />
                        <Toggle label="Caixa atrás do texto" checked={sel.backgroundEnabled} onChange={(v) => updateLayer(sel.id, { backgroundEnabled: v })} />
                      </div>
                      {sel.backgroundEnabled && (
                        <div className="grid gap-3 sm:grid-cols-[auto_1fr_1fr] sm:items-end">
                          <Swatch label="Cor da caixa" value={sel.backgroundColor} onChange={(v) => updateLayer(sel.id, { backgroundColor: v })} />
                          <Range label="Opacidade da caixa" value={sel.backgroundOpacity} min={0} max={100} onChange={(v) => updateLayer(sel.id, { backgroundOpacity: v })} suffix="%" />
                          <Range label="Margem da caixa" value={sel.backgroundPadding} min={0} max={60} onChange={(v) => updateLayer(sel.id, { backgroundPadding: v })} suffix="px" />
                        </div>
                      )}
                    </Group>

                    <Group title="Animação">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <select className="input" value={sel.animation} aria-label="Animação de entrada"
                          onChange={(e) => { updateLayer(sel.id, { animation: e.target.value as Layer["animation"] }); setAnimKey((k) => k + 1); }}>
                          {ANIMATIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
                        </select>
                        <Choice value={sel.showMode} onChange={(v) => updateLayer(sel.id, { showMode: v })}
                          options={[{ value: "always", label: "O clipe todo" }, { value: "start", label: "Início" }, { value: "end", label: "Final" }]} />
                      </div>
                      {sel.showMode !== "always" && (
                        <Range label={sel.showMode === "start" ? "Primeiros segundos" : "Últimos segundos"} value={sel.showSeconds}
                          min={0.5} max={30} step={0.5} onChange={(v) => updateLayer(sel.id, { showSeconds: v })} suffix="s" />
                      )}
                    </Group>
                  </div>
                )}
              </>
            )}

            {/* ---------------------------------------------- bordas */}
            {panel === "bordas" && (
              <>
                <Group title="Estilo rápido">
                  <div className="flex flex-wrap gap-1.5">
                    {BORDER_STYLES.map((s) => (
                      <button key={s.key} type="button" className="btn-ghost h-8 px-3 text-xs" onClick={() => applyBorderStyle(s.edges)}>
                        {s.label}
                      </button>
                    ))}
                  </div>
                </Group>

                <Group title="Cada borda" right={
                  <span className="flex items-center gap-2 text-[11px] text-zinc-400">
                    Mesma cor em todas
                    <Swatch label="Mesma cor em todas" value={cfg.frame.top.color} onChange={colorAllEdges} />
                  </span>
                }>
                  <div className="space-y-2" data-testid="edges">
                    {EDGES.map(({ key, label, max }) => {
                      const e = cfg.frame[key];
                      return (
                        <div key={key} className={`grid grid-cols-[7.5rem_1fr_auto] items-center gap-3 rounded-lg px-3 py-2 ring-1 transition ${
                          e.enabled ? "bg-white/5 ring-white/10" : "ring-white/5"}`} data-testid={`edge-${key}`}>
                          <Toggle label={label} checked={e.enabled} onChange={(v) => updateEdge(key, { enabled: v })} />
                          <Range label={key === "top" || key === "bottom" ? "Altura" : "Largura"} value={e.size} min={0.5} max={max} step={0.5}
                            disabled={!e.enabled} onChange={(v) => updateEdge(key, { size: v, enabled: true })} suffix="%" />
                          <Swatch label={`Cor da borda ${label.toLowerCase()}`} value={e.color} disabled={!e.enabled}
                            onChange={(v) => updateEdge(key, { color: v })} />
                        </div>
                      );
                    })}
                  </div>
                </Group>

                <Group title="Linha interna (borda de 2 cores)">
                  <div className={`grid items-end gap-3 sm:grid-cols-[1fr_auto] ${anyEdge ? "" : "opacity-40"}`}>
                    <Range label="Espessura (% de cada borda)" value={cfg.frame.innerPercent ?? 0} min={0} max={60}
                      disabled={!anyEdge} onChange={(v) => updateFrame({ innerPercent: v })} suffix="%" />
                    <Swatch label="Cor da linha interna" value={cfg.frame.color2 ?? "#000000"} disabled={!anyEdge}
                      onChange={(v) => updateFrame({ color2: v, innerPercent: cfg.frame.innerPercent || 20 })} />
                  </div>
                  {!anyEdge && <p className="text-[11px] text-zinc-500">Ligue pelo menos uma borda para usar a linha interna.</p>}
                </Group>
              </>
            )}

            {/* ---------------------------------------------- vídeo */}
            {panel === "video" && (
              <>
                <Choice label="Formato" value={cfg.aspectRatio}
                  onChange={(v) => { const a = ASPECTS.find((x) => x.value === v)!; update({ aspectRatio: v, width: a.width, height: a.height }); }}
                  options={ASPECTS.map((a) => ({ value: a.value, label: `${a.value} · ${a.hint}` }))} />
                <Choice label="Como o vídeo ocupa a tela" value={cfg.fitMode} onChange={(v) => update({ fitMode: v })}
                  options={[{ value: "cover", label: "Preencher" }, { value: "blur", label: "Inteiro + desfoque" }, { value: "contain", label: "Inteiro + cor" }]} />
                <div className="grid gap-3 sm:grid-cols-2">
                  <Range label="Zoom no vídeo" value={cfg.videoZoom} min={50} max={200} onChange={(v) => update({ videoZoom: v })} suffix="%" />
                  <Color label="Cor de fundo" value={cfg.backgroundColor} onChange={(v) => update({ backgroundColor: v })} />
                  <Color label="Cor de destaque (novas etiquetas)" value={cfg.accentColor} onChange={(v) => update({ accentColor: v })} />
                  <Toggle label="Vinheta (cantos escurecidos)" checked={cfg.vignette} onChange={(v) => update({ vignette: v })} />
                </div>
                <p className="text-[11px] text-zinc-500">
                  Se o projeto usar “webcam em cima + jogo embaixo”, esse layout é mantido e o template entra por cima.
                </p>
              </>
            )}

            {/* ---------------------------------------------- legendas */}
            {panel === "legendas" && (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <select className="input" value={cfg.captions.fontFamily} aria-label="Fonte da legenda"
                    onChange={(e) => updateCaps({ fontFamily: e.target.value })}>
                    {Object.entries(fontGroups).map(([g, fs]) => (
                      <optgroup key={g} label={g}>{fs.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</optgroup>
                    ))}
                  </select>
                  <Range label="Tamanho" value={cfg.captions.fontSize} min={10} max={200} onChange={(v) => updateCaps({ fontSize: v })} suffix="px" />
                  <Color label="Cor" value={cfg.captions.color} onChange={(v) => updateCaps({ color: v })} />
                  <Color label="Cor da palavra falada" value={cfg.captions.highlightColor} onChange={(v) => updateCaps({ highlightColor: v })} />
                  <div className="flex items-end gap-3">
                    <div className="flex-1"><Range label="Contorno" value={cfg.captions.outlineWidth} min={0} max={20} step={0.5} onChange={(v) => updateCaps({ outlineWidth: v })} suffix="px" /></div>
                    <Swatch label="Cor do contorno" value={cfg.captions.outlineColor} onChange={(v) => updateCaps({ outlineColor: v })} />
                  </div>
                  <Range label="Posição vertical" value={cfg.captions.y} min={5} max={95} step={0.5} onChange={(v) => updateCaps({ y: v })} suffix="%" />
                  <Range label="Palavras por vez" value={cfg.captions.wordsPerLine} min={1} max={8} onChange={(v) => updateCaps({ wordsPerLine: v })} />
                  <div className="space-y-2">
                    <Toggle label="MAIÚSCULAS" checked={cfg.captions.uppercase} onChange={(v) => updateCaps({ uppercase: v })} />
                    <Toggle label="Palavra falada “pula”" checked={cfg.captions.animation === "pop"}
                      onChange={(v) => updateCaps({ animation: v ? "pop" : "none" })} />
                  </div>
                </div>
                <p className="text-[11px] text-zinc-500">
                  A legenda aparece no vídeo só se estiver ligada no projeto. Para esconder o exemplo da tela, desligue
                  “Legenda de exemplo” embaixo da prévia.
                </p>
              </>
            )}

            {/* ---------------------------------------------- extras */}
            {panel === "extras" && (
              <Group title="Barra de progresso" right={
                <Toggle label="" checked={cfg.progressBar.enabled} onChange={(v) => updateBar({ enabled: v })} />
              }>
                {cfg.progressBar.enabled ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Color label="Cor" value={cfg.progressBar.color} onChange={(v) => updateBar({ color: v })} />
                    <Range label="Espessura" value={cfg.progressBar.heightPercent} min={0.2} max={5} step={0.1} onChange={(v) => updateBar({ heightPercent: v })} suffix="%" />
                    <Choice label="Posição" value={cfg.progressBar.position} onChange={(v) => updateBar({ position: v })}
                      options={[{ value: "top", label: "Topo" }, { value: "bottom", label: "Embaixo" }]} />
                  </div>
                ) : (
                  <p className="text-[11px] text-zinc-500">Uma barrinha que enche conforme o clipe avança.</p>
                )}
              </Group>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

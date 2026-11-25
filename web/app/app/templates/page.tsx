"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import TemplateCanvas from "@/components/TemplateCanvas";
import { Choice, Color, Range, Section, Toggle } from "@/components/ui";
import { api, API_URL, getToken, Project } from "@/lib/api";
import {
  ANIMATIONS, ASPECTS, blankConfig, CaptionStyle, defaultLayer, Frame, Layer, LayerKind, MAX_LAYERS, newId,
  Preset, ProgressBar, Template, TemplateConfig, TemplateOptions,
} from "@/lib/templates";

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

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
  const [showSampleCap, setShowSampleCap] = useState(true);

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewProject, setPreviewProject] = useState("");
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
  const updateFrame = (patch: Partial<Frame>) => update({ frame: { ...cfg.frame, ...patch } });
  const updateCaps = (patch: Partial<CaptionStyle>) => update({ captions: { ...cfg.captions, ...patch } });
  const updateBar = (patch: Partial<ProgressBar>) => update({ progressBar: { ...cfg.progressBar, ...patch } });
  const updateLayer = (id: string, patch: Partial<Layer>) => {
    setCfg((c) => ({ ...c, layers: c.layers.map((l) => (l.id === id ? { ...l, ...patch } : l)) }));
    setDirty(true);
  };
  const sel = cfg.layers.find((l) => l.id === selectedId) ?? null;

  function load(config: TemplateConfig, opts2: { name: string; id?: string | null; isDefault?: boolean }) {
    const c = clone(config);
    setCfg(c);
    setSelectedId(c.layers[0]?.id ?? null);
    setName(opts2.name);
    setEditingId(opts2.id ?? null);
    setIsDefault(Boolean(opts2.isDefault));
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

  async function realPreview() {
    setPreviewBusy(true);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const tok = getToken();
      if (tok) headers.Authorization = `Bearer ${tok}`;
      const res = await fetch(`${API_URL}/templates/preview`, {
        method: "POST", headers, body: JSON.stringify({ config: cfg, project_id: previewProject || null, captions: showSampleCap }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? "Falha na prévia");
      const blob = await res.blob();
      setPreviewUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return URL.createObjectURL(blob);
      });
    } catch (e) {
      setNotice({ ok: false, text: e instanceof Error ? e.message : "Falha na prévia" });
    } finally {
      setPreviewBusy(false);
    }
  }

  const categories = ["Todos", ...Array.from(new Set(presets.map((p) => p.category)))];
  const shownPresets = category === "Todos" ? presets : presets.filter((p) => p.category === category);

  // ------------------------------------------------------------ UI
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Templates</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Textos, fontes, efeitos e molduras aplicados automaticamente em todos os clipes. Use variáveis como{" "}
            <code className="text-violet-300">{"{titulo}"}</code> e <code className="text-violet-300">{"{gancho}"}</code>{" "}
            para cada clipe receber o seu próprio texto.
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
              <article key={t.id} className={`card card-hover flex flex-col overflow-hidden ${t.id === editingId ? "ring-2 ring-violet-500" : ""}`}>
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
      <section id="editor" className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">
              {editingId ? "Editando" : "Novo"}: <span className="text-violet-300">{name || "sem nome"}</span>
              {dirty && <span className="ml-2 text-xs text-amber-400">• não salvo</span>}
            </h2>
          </div>
          <div className="mx-auto overflow-hidden rounded-xl border border-zinc-800"
            style={{ maxWidth: cfg.width >= cfg.height ? "100%" : "360px" }}>
            <TemplateCanvas cfg={cfg} families={families} selectedId={selectedId} onSelect={setSelectedId}
              onMove={(id, x, y) => updateLayer(id, { x, y })} animateKey={animKey} showCaptions={showSampleCap} />
          </div>
          <p className="text-[11px] text-zinc-500">
            Arraste os textos na tela. A linha tracejada é a área segura (fora dela a interface do TikTok/Reels pode cobrir).
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <button className="btn-ghost text-xs" onClick={() => setAnimKey((k) => k + 1)}>▶ Ver animações</button>
            <button className="btn-ghost text-xs" onClick={distribute}>Centralizar e distribuir</button>
            <Toggle label="Legenda de exemplo" checked={showSampleCap} onChange={setShowSampleCap} />
          </div>
          <div className="card space-y-2 p-3">
            <span className="label">Prévia real (mesmo motor do vídeo final)</span>
            <div className="flex gap-2">
              <select className="input text-xs" value={previewProject} onChange={(e) => setPreviewProject(e.target.value)}>
                <option value="">Fundo de exemplo</option>
                {projects.map((p) => <option key={p.id} value={p.id}>Vídeo: {p.title}</option>)}
              </select>
              <button className="btn shrink-0 text-xs" onClick={realPreview} disabled={previewBusy}>
                {previewBusy ? "Gerando…" : "Gerar"}
              </button>
            </div>
            {previewUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={previewUrl} alt="Prévia renderizada" className="mx-auto w-full rounded-lg border border-zinc-800"
                style={{ maxWidth: cfg.width >= cfg.height ? "100%" : "360px" }} data-testid="real-preview" />
            )}
          </div>
        </div>

        <div className="space-y-3">
          {/* salvar */}
          <div className="card space-y-3 p-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[200px] flex-1">
                <label className="label" htmlFor="tpl-name">Nome do template</label>
                <input id="tpl-name" className="input" maxLength={60} value={name}
                  onChange={(e) => { setName(e.target.value); setDirty(true); }} />
              </div>
              <label className="flex items-center gap-2 pb-2 text-xs text-zinc-300">
                <input type="checkbox" checked={isDefault} onChange={(e) => { setIsDefault(e.target.checked); setDirty(true); }}
                  className="h-4 w-4 accent-violet-500" />
                Usar em todos os projetos novos (padrão)
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              {editingId && <button className="btn" onClick={() => save(false)} disabled={!name.trim()}>Salvar alterações</button>}
              <button className={editingId ? "btn-ghost" : "btn"} onClick={() => save(true)} disabled={!name.trim()}>
                {editingId ? "Salvar como novo" : "Salvar na biblioteca"}
              </button>
            </div>
          </div>

          {/* camadas */}
          <Section title={`Textos (${cfg.layers.length}/${MAX_LAYERS})`}>
            <div className="flex flex-wrap gap-2">
              <button className="btn-ghost text-xs" onClick={() => addLayer("title")} disabled={cfg.layers.length >= MAX_LAYERS}>+ Título</button>
              <button className="btn-ghost text-xs" onClick={() => addLayer("text")} disabled={cfg.layers.length >= MAX_LAYERS}>+ Texto</button>
              <button className="btn-ghost text-xs" onClick={() => addLayer("tag")} disabled={cfg.layers.length >= MAX_LAYERS}>+ Etiqueta</button>
            </div>
            <ul className="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
              {cfg.layers.map((l, i) => (
                <li key={l.id} className={`flex items-center gap-2 px-3 py-2 text-sm ${l.id === selectedId ? "bg-violet-500/10" : ""}`}>
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
          </Section>

          {sel && (
            <Section title="Texto selecionado">
              <div>
                <label className="label" htmlFor="layer-text">Texto</label>
                <textarea id="layer-text" className="input min-h-[64px] font-mono" maxLength={300} value={sel.text}
                  onChange={(e) => updateLayer(sel.id, { text: e.target.value })} />
                <div className="mt-2 flex flex-wrap gap-1">
                  {Object.entries(opts?.variables ?? {}).map(([k, desc]) => (
                    <button key={k} type="button" title={desc} onClick={() => insertVar(k)}
                      className="rounded bg-violet-500/15 px-2 py-0.5 font-mono text-[11px] text-violet-200 hover:bg-violet-500/30">
                      {`{${k}}`}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="layer-font">Fonte</label>
                  <select id="layer-font" className="input" value={sel.fontFamily}
                    onChange={(e) => updateLayer(sel.id, { fontFamily: e.target.value })}
                    style={{ fontFamily: `"${families[sel.fontFamily]}"` }}>
                    {Object.entries(fontGroups).map(([g, fs]) => (
                      <optgroup key={g} label={g}>
                        {fs.map((f) => <option key={f.key} value={f.key} style={{ fontFamily: `"${f.family}"` }}>{f.label}</option>)}
                      </optgroup>
                    ))}
                  </select>
                </div>
                <Choice label="Alinhamento" value={sel.align} onChange={(v) => updateLayer(sel.id, { align: v })}
                  options={[{ value: "left", label: "Esquerda" }, { value: "center", label: "Centro" }, { value: "right", label: "Direita" }]} />
              </div>

              <div className="flex flex-wrap gap-4">
                <Toggle label="Negrito" checked={sel.bold} onChange={(v) => updateLayer(sel.id, { bold: v })} />
                <Toggle label="Itálico" checked={sel.italic} onChange={(v) => updateLayer(sel.id, { italic: v })} />
                <Toggle label="MAIÚSCULAS" checked={sel.uppercase} onChange={(v) => updateLayer(sel.id, { uppercase: v })} />
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <Range label="Tamanho" value={sel.fontSize} min={10} max={200} onChange={(v) => updateLayer(sel.id, { fontSize: v })} suffix="px" />
                <Range label="Largura máxima" value={sel.boxWidth} min={10} max={100} onChange={(v) => updateLayer(sel.id, { boxWidth: v })} suffix="%" />
                <Range label="Posição horizontal" value={sel.x} min={0} max={100} step={0.5} onChange={(v) => updateLayer(sel.id, { x: v })} suffix="%" />
                <Range label="Posição vertical" value={sel.y} min={0} max={100} step={0.5} onChange={(v) => updateLayer(sel.id, { y: v })} suffix="%" />
                <Range label="Espaçamento entre letras" value={sel.letterSpacing} min={-10} max={60} onChange={(v) => updateLayer(sel.id, { letterSpacing: v })} suffix="px" />
                <Range label="Inclinação" value={sel.rotation} min={-45} max={45} onChange={(v) => updateLayer(sel.id, { rotation: v })} suffix="°" />
                <Color label="Cor do texto" value={sel.color} onChange={(v) => updateLayer(sel.id, { color: v })} />
                <Range label="Opacidade" value={sel.opacity} min={0} max={100} onChange={(v) => updateLayer(sel.id, { opacity: v })} suffix="%" />
              </div>

              <div className="space-y-3 rounded-lg border border-zinc-800 p-3">
                <span className="label">Efeitos</span>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Range label="Contorno" value={sel.outlineWidth} min={0} max={30} step={0.5} onChange={(v) => updateLayer(sel.id, { outlineWidth: v })} suffix="px" />
                  <Color label="Cor do contorno / brilho" value={sel.outlineColor} onChange={(v) => updateLayer(sel.id, { outlineColor: v })} />
                  <Range label="Sombra" value={sel.shadowDepth} min={0} max={30} step={0.5} onChange={(v) => updateLayer(sel.id, { shadowDepth: v })} suffix="px" />
                  <Color label="Cor da sombra" value={sel.shadowColor} onChange={(v) => updateLayer(sel.id, { shadowColor: v })} />
                  <Range label="Opacidade da sombra" value={sel.shadowOpacity} min={0} max={100} onChange={(v) => updateLayer(sel.id, { shadowOpacity: v })} suffix="%" />
                  <Toggle label="Brilho neon" checked={sel.glow} onChange={(v) => updateLayer(sel.id, { glow: v })} />
                </div>
                <Toggle label="Caixa atrás do texto (desliga o contorno)" checked={sel.backgroundEnabled}
                  onChange={(v) => updateLayer(sel.id, { backgroundEnabled: v })} />
                {sel.backgroundEnabled && (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Color label="Cor da caixa" value={sel.backgroundColor} onChange={(v) => updateLayer(sel.id, { backgroundColor: v })} />
                    <Range label="Opacidade da caixa" value={sel.backgroundOpacity} min={0} max={100} onChange={(v) => updateLayer(sel.id, { backgroundOpacity: v })} suffix="%" />
                    <Range label="Margem da caixa" value={sel.backgroundPadding} min={0} max={60} onChange={(v) => updateLayer(sel.id, { backgroundPadding: v })} suffix="px" />
                  </div>
                )}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="label" htmlFor="layer-anim">Animação de entrada</label>
                  <select id="layer-anim" className="input" value={sel.animation}
                    onChange={(e) => { updateLayer(sel.id, { animation: e.target.value as Layer["animation"] }); setAnimKey((k) => k + 1); }}>
                    {ANIMATIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
                  </select>
                </div>
                <Choice label="Quando mostrar" value={sel.showMode} onChange={(v) => updateLayer(sel.id, { showMode: v })}
                  options={[{ value: "always", label: "O clipe todo" }, { value: "start", label: "No início" }, { value: "end", label: "No final" }]} />
                {sel.showMode !== "always" && (
                  <Range label={sel.showMode === "start" ? "Primeiros segundos" : "Últimos segundos"} value={sel.showSeconds}
                    min={0.5} max={30} step={0.5} onChange={(v) => updateLayer(sel.id, { showSeconds: v })} suffix="s" />
                )}
              </div>
            </Section>
          )}

          <Section title="Formato e vídeo" open={false}>
            <Choice label="Formato" value={cfg.aspectRatio}
              onChange={(v) => { const a = ASPECTS.find((x) => x.value === v)!; update({ aspectRatio: v, width: a.width, height: a.height }); }}
              options={ASPECTS.map((a) => ({ value: a.value, label: `${a.value} · ${a.hint}` }))} />
            <Choice label="Como o vídeo ocupa a tela" value={cfg.fitMode} onChange={(v) => update({ fitMode: v })}
              options={[{ value: "cover", label: "Preencher (corta as laterais)" }, { value: "blur", label: "Inteiro + fundo desfocado" }, { value: "contain", label: "Inteiro + fundo sólido" }]} />
            <div className="grid gap-3 sm:grid-cols-2">
              <Range label="Zoom no vídeo" value={cfg.videoZoom} min={50} max={200} onChange={(v) => update({ videoZoom: v })} suffix="%" />
              <Color label="Cor de fundo" value={cfg.backgroundColor} onChange={(v) => update({ backgroundColor: v })} />
              <Color label="Cor de destaque (novas etiquetas)" value={cfg.accentColor} onChange={(v) => update({ accentColor: v })} />
              <Toggle label="Vinheta (bordas escurecidas)" checked={cfg.vignette} onChange={(v) => update({ vignette: v })} />
            </div>
            <p className="text-[11px] text-zinc-500">
              Se o projeto usar o layout “webcam em cima + jogo embaixo”, ele é mantido e o template aplica textos e molduras por cima.
            </p>
          </Section>

          <Section title="Moldura e barra de progresso" open={false}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Toggle label="Faixa no topo (cabeçalho)" checked={cfg.frame.headerBorder} onChange={(v) => updateFrame({ headerBorder: v })} />
              <Toggle label="Faixa embaixo (rodapé)" checked={cfg.frame.footerBorder} onChange={(v) => updateFrame({ footerBorder: v })} />
              <Toggle label="Bordas laterais" checked={cfg.frame.sideBorders} onChange={(v) => updateFrame({ sideBorders: v })} />
              <Color label="Cor da moldura" value={cfg.frame.color} onChange={(v) => updateFrame({ color: v })} />
              {cfg.frame.headerBorder && <Range label="Altura do cabeçalho" value={cfg.frame.headerHeightPercent} min={1} max={45} step={0.5} onChange={(v) => updateFrame({ headerHeightPercent: v })} suffix="%" />}
              {cfg.frame.footerBorder && <Range label="Altura do rodapé" value={cfg.frame.footerHeightPercent} min={1} max={45} step={0.5} onChange={(v) => updateFrame({ footerHeightPercent: v })} suffix="%" />}
              {cfg.frame.sideBorders && <Range label="Largura das bordas" value={cfg.frame.sideWidthPercent} min={0.5} max={45} step={0.5} onChange={(v) => updateFrame({ sideWidthPercent: v })} suffix="%" />}
            </div>
            {(cfg.frame.headerBorder || cfg.frame.footerBorder || cfg.frame.sideBorders) && (
              <div className="grid gap-3 rounded-lg border border-zinc-800 p-3 sm:grid-cols-2">
                <span className="label sm:col-span-2">Borda personalizada (linha interna de 2ª cor)</span>
                <Range label="Espessura da linha interna" value={cfg.frame.innerPercent ?? 0} min={0} max={60} step={1}
                  onChange={(v) => updateFrame({ innerPercent: v })} suffix="%" />
                {(cfg.frame.innerPercent ?? 0) > 0 &&
                  <Color label="Cor da linha interna" value={cfg.frame.color2 ?? "#000000"} onChange={(v) => updateFrame({ color2: v })} />}
              </div>
            )}
            <div className="space-y-3 rounded-lg border border-zinc-800 p-3">
              <Toggle label="Barra de progresso do clipe" checked={cfg.progressBar.enabled} onChange={(v) => updateBar({ enabled: v })} />
              {cfg.progressBar.enabled && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Color label="Cor" value={cfg.progressBar.color} onChange={(v) => updateBar({ color: v })} />
                  <Range label="Espessura" value={cfg.progressBar.heightPercent} min={0.2} max={5} step={0.1} onChange={(v) => updateBar({ heightPercent: v })} suffix="%" />
                  <Choice label="Posição" value={cfg.progressBar.position} onChange={(v) => updateBar({ position: v })}
                    options={[{ value: "top", label: "Topo" }, { value: "bottom", label: "Embaixo" }]} />
                </div>
              )}
            </div>
          </Section>

          <Section title="Legendas automáticas (fala)" open={false}>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="cap-font">Fonte</label>
                <select id="cap-font" className="input" value={cfg.captions.fontFamily} onChange={(e) => updateCaps({ fontFamily: e.target.value })}>
                  {Object.entries(fontGroups).map(([g, fs]) => (
                    <optgroup key={g} label={g}>{fs.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</optgroup>
                  ))}
                </select>
              </div>
              <Range label="Tamanho" value={cfg.captions.fontSize} min={10} max={200} onChange={(v) => updateCaps({ fontSize: v })} suffix="px" />
              <Color label="Cor" value={cfg.captions.color} onChange={(v) => updateCaps({ color: v })} />
              <Color label="Cor da palavra falada" value={cfg.captions.highlightColor} onChange={(v) => updateCaps({ highlightColor: v })} />
              <Color label="Cor do contorno" value={cfg.captions.outlineColor} onChange={(v) => updateCaps({ outlineColor: v })} />
              <Range label="Contorno" value={cfg.captions.outlineWidth} min={0} max={20} step={0.5} onChange={(v) => updateCaps({ outlineWidth: v })} suffix="px" />
              <Range label="Posição vertical" value={cfg.captions.y} min={5} max={95} step={0.5} onChange={(v) => updateCaps({ y: v })} suffix="%" />
              <Range label="Palavras por vez" value={cfg.captions.wordsPerLine} min={1} max={8} onChange={(v) => updateCaps({ wordsPerLine: v })} />
              <Toggle label="MAIÚSCULAS" checked={cfg.captions.uppercase} onChange={(v) => updateCaps({ uppercase: v })} />
              <Toggle label="Palavra falada “pula” (pop)" checked={cfg.captions.animation === "pop"}
                onChange={(v) => updateCaps({ animation: v ? "pop" : "none" })} />
            </div>
            <p className="text-[11px] text-zinc-500">As legendas podem ser ligadas ou desligadas em cada projeto.</p>
          </Section>
        </div>
      </section>
    </div>
  );
}

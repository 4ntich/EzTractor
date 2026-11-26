"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Choice } from "@/components/ui";
import { api, copyText, SystemInfo, ViralItem, ViralResult } from "@/lib/api";

type Period = "today" | "week" | "month" | "year" | "any";
type Kind = "shorts" | "videos" | "any";
type Sort = "trending" | "views" | "engagement";

const compact = (n: number) => new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(n);
const dur = (s: number | null) => (s == null ? "" : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
function age(h: number | null) {
  if (h == null) return "";
  if (h < 24) return `há ${Math.max(1, Math.round(h))} h`;
  const d = Math.round(h / 24);
  if (d < 31) return `há ${d} dia${d > 1 ? "s" : ""}`;
  const m = Math.round(d / 30);
  return m < 12 ? `há ${m} ${m > 1 ? "meses" : "mês"}` : `há ${Math.round(d / 365)} ano(s)`;
}

const LS = "ezt-viral-last";

export default function ViraisPage() {
  const router = useRouter();
  const [sys, setSys] = useState<SystemInfo | null>(null);
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  const [q, setQ] = useState("");
  const [period, setPeriod] = useState<Period>("week");
  const [kind, setKind] = useState<Kind>("shorts");
  const [sort, setSort] = useState<Sort>("trending");
  const [region, setRegion] = useState("BR");
  const [limit, setLimit] = useState(25);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<ViralResult | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [setup, setSetup] = useState(false);

  useEffect(() => {
    api<SystemInfo>("/system/info").then(setSys).catch(() => {});
    api<{ configured: boolean }>("/system/youtube").then((r) => setHasKey(r.configured)).catch(() => setHasKey(false));
    try { // última busca (só neste aparelho)
      const last = JSON.parse(localStorage.getItem(LS) ?? "null");
      if (last) { setQ(last.q ?? ""); setPeriod(last.period ?? "week"); setKind(last.kind ?? "shorts"); setSort(last.sort ?? "trending"); setRegion(last.region ?? "BR"); }
    } catch { /* ignora */ }
  }, []);

  async function search(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const p = new URLSearchParams({ q, period, kind, sort, region, limit: String(limit) });
      setRes(await api<ViralResult>(`/viral/search?${p}`));
      try { localStorage.setItem(LS, JSON.stringify({ q, period, kind, sort, region })); } catch { /* ignora */ }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro na busca");
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string, id: string) {
    if (await copyText(text)) {
      setCopied(id);
      setTimeout(() => setCopied(null), 1800);
    }
  }

  const numbers = res?.source === "api";

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">🔥 Descobrir virais</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Busca no YouTube os vídeos e Shorts que mais estão bombando sobre um jogo ou tema. Copie os links ou mande direto
          para o EzTractor cortar.
        </p>
      </header>

      <KeyCard hasKey={hasKey} isLocal={Boolean(sys?.is_local)} open={setup} onOpen={setSetup}
        onChange={(v) => { setHasKey(v); setRes(null); }} />

      <form onSubmit={search} className="card space-y-4 p-5" data-testid="viral-form">
        <div className="flex flex-wrap gap-2">
          <input className="input min-w-[220px] flex-1" placeholder="Ex.: Free Fire capa, Valorant clutch, GTA RP engraçado"
            value={q} onChange={(e) => setQ(e.target.value)} aria-label="Jogo ou tema" data-testid="viral-q" />
          <button className="btn" disabled={busy || !q.trim()} data-testid="viral-search">{busy ? "Buscando…" : "Buscar"}</button>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-3">
          <Choice label="Publicado" value={period} onChange={setPeriod} options={[
            { value: "today", label: "Hoje" }, { value: "week", label: "Semana" }, { value: "month", label: "Mês" },
            { value: "year", label: "Ano" }, { value: "any", label: "Qualquer data" }]} />
          <Choice label="Tipo" value={kind} onChange={setKind} options={[
            { value: "shorts", label: "Shorts" }, { value: "videos", label: "Vídeos" }, { value: "any", label: "Todos" }]} />
          <div className={hasKey ? "" : "pointer-events-none opacity-50"} title={hasKey ? "" : "Precisa da chave do YouTube"}>
            <Choice label="Ordenar" value={sort} onChange={setSort} options={[
              { value: "trending", label: "🔥 Viralizando" }, { value: "views", label: "Mais vistos" },
              { value: "engagement", label: "Engajamento" }]} />
          </div>
          <div>
            <span className="label">País</span>
            <select className="input h-9 py-1 text-xs" value={region} onChange={(e) => setRegion(e.target.value)} aria-label="País">
              <option value="BR">Brasil</option><option value="PT">Portugal</option><option value="US">EUA</option>
              <option value="MX">México</option><option value="ES">Espanha</option><option value="">Mundo todo</option>
            </select>
          </div>
          <div>
            <span className="label">Quantos</span>
            <select className="input h-9 py-1 text-xs" value={limit} onChange={(e) => setLimit(Number(e.target.value))} aria-label="Quantidade">
              {[10, 25, 50].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </div>
        {!hasKey && hasKey !== null && (
          <p className="text-[11px] text-zinc-500">Sem chave, a lista vem na ordem de “mais vistos” do período, sem os números.</p>
        )}
      </form>

      {error && <p className="rounded-lg bg-red-500/15 px-3 py-2 text-sm text-danger ring-1 ring-red-400/30">{error}</p>}

      {res && (
        <section className="space-y-3" data-testid="viral-results">
          {res.notice && (
            <p className="rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-200 ring-1 ring-amber-400/30">{res.notice}</p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-zinc-400">
              {res.results.length} resultado(s) · {numbers ? (sort === "trending" ? "ordenados pelo que mais está viralizando (visualizações por dia)" : sort === "views" ? "ordenados por visualizações" : "ordenados por engajamento") : "ordem de mais vistos do YouTube"}
            </p>
            {res.results.length > 0 && (
              <button className="btn-ghost h-9 px-3 text-xs" data-testid="copy-all"
                onClick={() => copy(res.results.map((r) => r.url).join("\n"), "all")}>
                {copied === "all" ? "✓ Links copiados!" : "📋 Copiar todos os links"}
              </button>
            )}
          </div>
          {res.results.length === 0 ? (
            <p className="text-sm text-zinc-500">Nada encontrado. Tente outro termo ou um período maior.</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {res.results.map((v, i) => (
                <Result key={v.id} v={v} rank={i + 1} numbers={numbers} copied={copied === v.id}
                  onCopy={() => copy(v.url, v.id)} onCut={() => router.push(`/app?url=${encodeURIComponent(v.url)}`)} />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function Result({ v, rank, numbers, copied, onCopy, onCut }: {
  v: ViralItem; rank: number; numbers: boolean; copied: boolean; onCopy: () => void; onCut: () => void;
}) {
  return (
    <article className="card flex flex-col overflow-hidden" data-testid="viral-item">
      <a href={v.url} target="_blank" rel="noreferrer" className="relative block aspect-video bg-black">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={v.thumbnail} alt="" loading="lazy" className="h-full w-full object-cover"
          onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
        <span className="absolute left-2 top-2 rounded-full bg-black/75 px-2 py-0.5 text-xs font-bold text-onvideo">#{rank}</span>
        {v.is_short && <span className="absolute right-2 top-2 rounded-full bg-red-600 px-2 py-0.5 text-[10px] font-bold text-onvideo">SHORT</span>}
        {v.duration_s != null && (
          <span className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 font-mono text-[11px] text-onvideo">{dur(v.duration_s)}</span>
        )}
      </a>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug" title={v.title}>{v.title}</h3>
        {v.channel && <p className="truncate text-xs text-zinc-400">{v.channel}</p>}
        {numbers && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-300">
            {v.views != null && <span title="Visualizações">👁 {compact(v.views)}</span>}
            {v.views_per_day != null && (
              <span className="font-semibold text-amber-300" title="Visualizações por dia desde que foi publicado">🔥 {compact(v.views_per_day)}/dia</span>
            )}
            {v.engagement != null && <span title="Curtidas por visualização">👍 {(v.engagement * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</span>}
            {v.age_hours != null && <span className="text-zinc-500">{age(v.age_hours)}</span>}
          </div>
        )}
        <div className="mt-auto flex gap-1.5 pt-2">
          <a className="btn-ghost h-8 flex-1 px-2 text-xs" href={v.url} target="_blank" rel="noreferrer">▶ Abrir</a>
          <button className="btn-ghost h-8 px-2 text-xs" onClick={onCopy}>{copied ? "✓" : "📋 Link"}</button>
          <button className="btn h-8 px-2 text-xs" onClick={onCut} title="Criar um projeto com este vídeo">✂ Cortar</button>
        </div>
      </div>
    </article>
  );
}

/** Situação da chave do YouTube + passo a passo para criar uma grátis. */
function KeyCard({ hasKey, isLocal, open, onOpen, onChange }: {
  hasKey: boolean | null; isLocal: boolean; open: boolean; onOpen: (v: boolean) => void; onChange: (v: boolean) => void;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (hasKey === null) return null;

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      await api("/system/youtube", { method: "POST", body: JSON.stringify({ key }) });
      setKey("");
      onChange(true);
      onOpen(false);
      setMsg({ ok: true, text: "Chave testada e salva. Agora as buscas mostram visualizações e o que está viralizando." });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Erro" });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api("/system/youtube", { method: "DELETE" });
      onChange(false);
      setMsg({ ok: true, text: "Chave removida. As buscas voltam a ser sem números." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-3 p-4" data-testid="key-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {hasKey ? (
          <span className="inline-flex items-center gap-2 rounded-lg bg-emerald-500/15 px-3 py-1.5 text-sm text-emerald-300 ring-1 ring-emerald-400/30">
            ✓ Chave do YouTube ativa: visualizações, curtidas e “viralizando”
          </span>
        ) : (
          <p className="text-sm text-zinc-300">
            <b className="text-white">Sem chave do YouTube.</b> Com uma chave grátis você vê visualizações e o que está
            viralizando (cerca de 100 buscas por dia, sem cartão).
          </p>
        )}
        {isLocal && (hasKey ? (
          <div className="flex gap-2">
            <button className="btn-ghost h-9 px-3 text-xs" onClick={() => onOpen(!open)}>Trocar chave</button>
            <button className="btn-ghost h-9 px-3 text-xs text-danger" onClick={remove} disabled={busy}>Remover</button>
          </div>
        ) : (
          <button className="btn h-9 px-3 text-xs" onClick={() => onOpen(!open)} data-testid="setup-key">
            {open ? "Fechar" : "Configurar chave grátis"}
          </button>
        ))}
      </div>
      {!isLocal && !hasKey && <p className="text-xs text-zinc-500">A chave é configurada no computador onde o EzTractor está instalado.</p>}

      {open && isLocal && (
        <div className="space-y-3 rounded-xl bg-black/15 p-4 ring-1 ring-white/10">
          <ol className="list-decimal space-y-1.5 pl-5 text-sm text-zinc-300">
            <li>Abra o <a className="text-[rgb(var(--a-300))] underline" href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noreferrer">Google Cloud</a> (entre com sua conta Google) e crie um projeto, por exemplo “EzTractor”. É grátis.</li>
            <li>Ative a <a className="text-[rgb(var(--a-300))] underline" href="https://console.cloud.google.com/apis/library/youtube.googleapis.com" target="_blank" rel="noreferrer">YouTube Data API v3</a> nesse projeto (botão “Ativar”).</li>
            <li>Vá em <a className="text-[rgb(var(--a-300))] underline" href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">Credenciais</a> → “Criar credenciais” → “Chave de API” e copie a chave.</li>
            <li>Recomendado: em “Restringir chave”, escolha só a <i>YouTube Data API v3</i>.</li>
            <li>Cole aqui e salve. O EzTractor testa a chave antes de guardar (no computador, nunca é enviada para outro lugar).</li>
          </ol>
          <div className="flex flex-wrap gap-2">
            <input type="password" className="input min-w-[240px] flex-1 font-mono" placeholder="AIza…" autoComplete="off"
              value={key} onChange={(e) => setKey(e.target.value)} aria-label="Chave de API do YouTube" data-testid="key-input" />
            <button className="btn" onClick={save} disabled={busy || key.trim().length < 20} data-testid="key-save">
              {busy ? "Testando…" : "Testar e salvar"}
            </button>
          </div>
        </div>
      )}
      {msg && <p className={`rounded-lg px-3 py-2 text-sm ${msg.ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-danger"}`}>{msg.text}</p>}
    </section>
  );
}

"use client";

import { useState } from "react";

import { Clip, copyText } from "@/lib/api";

/** Prévia da legenda + hashtags e botão "Copiar legenda" (para colar no TikTok/Reels/Shorts). */
export default function CopyCaption({ clip, compact = false }: { clip: Clip; compact?: boolean }) {
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");

  async function copy() {
    const ok = await copyText(clip.social_text);
    setState(ok ? "ok" : "fail");
    setTimeout(() => setState("idle"), 2000);
  }

  if (!clip.social_text) return null;
  return (
    <div className="space-y-1.5" data-testid="caption-box">
      <button type="button" onClick={copy} title="Clique para copiar"
        className="block w-full rounded-lg bg-black/20 px-2.5 py-2 text-left text-xs ring-1 ring-white/10 transition hover:ring-[rgb(var(--a-400)/.6)]">
        <span className={`block whitespace-pre-line text-zinc-300 ${compact ? "line-clamp-2" : "line-clamp-4"}`}>{clip.caption}</span>
        {clip.hashtags.length > 0 && (
          <span className="mt-1 block truncate text-[rgb(var(--a-300))]">{clip.hashtags.join(" ")}</span>
        )}
      </button>
      <button type="button" className="btn-ghost h-8 w-full text-xs" onClick={copy} data-testid="copy-caption">
        {state === "ok" ? "✓ Legenda copiada!" : state === "fail" ? "Não deu para copiar — selecione o texto" : "📋 Copiar legenda"}
      </button>
    </div>
  );
}

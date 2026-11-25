"use client";

import { Fragment, useRef, useState } from "react";

import {
  cq, fillVars, Layer, layerPosition, layerTextStyle, SAMPLE_VARS, TemplateConfig,
} from "@/lib/templates";

type Props = {
  cfg: TemplateConfig;
  families: Record<string, string>; // chave da fonte -> família CSS
  background?: string;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  onMove?: (id: string, x: number, y: number) => void;
  animateKey?: number; // muda => reinicia as animações
  showCaptions?: boolean;
  className?: string;
};

const SNAP = 1.5; // % de distância para "grudar" no centro

export default function TemplateCanvas({
  cfg, families, background = "/sample-gameplay.jpg", selectedId, onSelect, onMove, animateKey = 0,
  showCaptions = true, className = "",
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: string; sx: number; sy: number; lx: number; ly: number } | null>(null);
  const [guides, setGuides] = useState<{ v: boolean; h: boolean }>({ v: false, h: false });
  const W = cfg.width;
  const interactive = Boolean(onMove);
  const fam = (k: string) => families[k] ?? "Poppins";
  const zoom = cfg.videoZoom / 100;

  function down(e: React.PointerEvent, l: Layer) {
    if (!interactive) return;
    e.stopPropagation();
    onSelect?.(l.id);
    drag.current = { id: l.id, sx: e.clientX, sy: e.clientY, lx: l.x, ly: l.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function move(e: React.PointerEvent) {
    const d = drag.current;
    const box = ref.current?.getBoundingClientRect();
    if (!d || !box || !onMove) return;
    let x = d.lx + ((e.clientX - d.sx) / box.width) * 100;
    let y = d.ly + ((e.clientY - d.sy) / box.height) * 100;
    const v = Math.abs(x - 50) < SNAP;
    const h = Math.abs(y - 50) < SNAP;
    if (v) x = 50;
    if (h) y = 50;
    setGuides({ v, h });
    onMove(d.id, Math.round(Math.max(0, Math.min(100, x)) * 2) / 2, Math.round(Math.max(0, Math.min(100, y)) * 2) / 2);
  }

  function up() {
    drag.current = null;
    setGuides({ v: false, h: false });
  }

  const f = cfg.frame;
  const cap = cfg.captions;
  const capWords = ["isso", "foi", "insano", "demais"].slice(0, Math.max(1, cap.wordsPerLine));

  return (
    <div
      ref={ref}
      className={`ezt-canvas relative w-full touch-none select-none overflow-hidden ${className}`}
      style={{ aspectRatio: `${cfg.width} / ${cfg.height}`, background: cfg.backgroundColor }}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onPointerDown={() => interactive && onSelect?.(null)}
    >
      {/* vídeo */}
      {cfg.fitMode === "blur" && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={background} alt="" draggable={false}
          className="absolute inset-0 h-full w-full scale-110 object-cover" style={{ filter: "blur(3cqw) brightness(.75)" }} />
      )}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={background} alt="" draggable={false}
        className={`absolute inset-0 h-full w-full ${cfg.fitMode === "cover" ? "object-cover" : "object-contain"}`}
        style={{ transform: `scale(${zoom})` }} />
      {cfg.vignette && (
        <div className="pointer-events-none absolute inset-0"
          style={{ background: "radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,.75) 100%)" }} />
      )}

      {/* moldura (+ linha interna de 2ª cor, se innerPercent > 0) */}
      {f.headerBorder && (
        <div className="absolute inset-x-0 top-0" style={{ height: `${f.headerHeightPercent}%`, background: f.color }}>
          {(f.innerPercent ?? 0) > 0 && <div className="absolute inset-x-0 bottom-0" style={{ height: `${f.innerPercent}%`, background: f.color2 }} />}
        </div>
      )}
      {f.footerBorder && (
        <div className="absolute inset-x-0 bottom-0" style={{ height: `${f.footerHeightPercent}%`, background: f.color }}>
          {(f.innerPercent ?? 0) > 0 && <div className="absolute inset-x-0 top-0" style={{ height: `${f.innerPercent}%`, background: f.color2 }} />}
        </div>
      )}
      {f.sideBorders && (
        <>
          <div className="absolute inset-y-0 left-0" style={{ width: `${f.sideWidthPercent}%`, background: f.color }}>
            {(f.innerPercent ?? 0) > 0 && <div className="absolute inset-y-0 right-0" style={{ width: `${f.innerPercent}%`, background: f.color2 }} />}
          </div>
          <div className="absolute inset-y-0 right-0" style={{ width: `${f.sideWidthPercent}%`, background: f.color }}>
            {(f.innerPercent ?? 0) > 0 && <div className="absolute inset-y-0 left-0" style={{ width: `${f.innerPercent}%`, background: f.color2 }} />}
          </div>
        </>
      )}
      {cfg.progressBar.enabled && (
        <div className={`absolute left-0 ${cfg.progressBar.position === "top" ? "top-0" : "bottom-0"}`}
          style={{ width: "40%", height: `${cfg.progressBar.heightPercent}%`, background: cfg.progressBar.color }} />
      )}

      {/* legenda de exemplo */}
      {showCaptions && (
        <div className="pointer-events-none absolute left-1/2 w-[92%] -translate-x-1/2 -translate-y-1/2 text-center"
          style={{
            top: `${cap.y}%`, fontFamily: `"${fam(cap.fontFamily)}"`, fontSize: cq(cap.fontSize, W), fontWeight: 700,
            textTransform: cap.uppercase ? "uppercase" : "none", color: cap.color, lineHeight: 1.1,
            WebkitTextStroke: cap.outlineWidth ? `${cq(cap.outlineWidth * 2, W)} ${cap.outlineColor}` : undefined,
            paintOrder: "stroke fill",
          }}>
          {capWords.map((w, i) => (
            <Fragment key={i}>
              {i > 0 && " "}
              <span style={i === Math.min(2, capWords.length - 1)
                ? { color: cap.highlightColor, display: "inline-block", transform: cap.animation === "pop" ? "scale(1.08)" : undefined }
                : undefined}>
                {w}
              </span>
            </Fragment>
          ))}
        </div>
      )}

      {/* camadas */}
      {cfg.layers.map((l) => {
        const text = fillVars(l.text, SAMPLE_VARS);
        const selected = selectedId === l.id;
        return (
          <div key={l.id} style={layerPosition(l)} onPointerDown={(e) => down(e, l)}
            className={interactive ? "cursor-move" : undefined}>
            <div key={animateKey} className={l.animation !== "none" ? `ezt-anim-${l.animation}` : undefined}
              style={{ outline: selected ? "2px dashed #a78bfa" : undefined, outlineOffset: "4px" }}>
              <span style={layerTextStyle(l, fam(l.fontFamily), W)}>{text || (interactive ? "(vazio)" : "")}</span>
            </div>
            {interactive && l.showMode !== "always" && (
              <span className="absolute -top-4 left-0 rounded bg-black/70 px-1 text-[9px] text-amber-300">
                {l.showMode === "start" ? `primeiros ${l.showSeconds}s` : `últimos ${l.showSeconds}s`}
              </span>
            )}
          </div>
        );
      })}

      {guides.v && <div className="pointer-events-none absolute inset-y-0 left-1/2 w-px bg-fuchsia-400" />}
      {guides.h && <div className="pointer-events-none absolute inset-x-0 top-1/2 h-px bg-fuchsia-400" />}
      {/* área segura (onde as interfaces do TikTok/Reels não cobrem) */}
      {interactive && (
        <div className="pointer-events-none absolute border border-dashed border-white/15"
          style={{ left: "6%", right: "16%", top: "9%", bottom: "20%" }} title="Área segura" />
      )}
    </div>
  );
}

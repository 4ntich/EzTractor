// Tipos e utilidades dos templates. Espelham backend/eztractor/schemas.py.
import type { CSSProperties } from "react";

export type LayerKind = "title" | "text" | "tag";
export type Align = "left" | "center" | "right";
export type Animation =
  | "none" | "fade" | "pop" | "slide-up" | "slide-down" | "slide-left" | "typewriter" | "pulse" | "zoom-in";

export type Layer = {
  id: string;
  kind: LayerKind;
  text: string;
  x: number;
  y: number;
  boxWidth: number;
  fontSize: number;
  color: string;
  opacity: number;
  align: Align;
  bold: boolean;
  italic: boolean;
  uppercase: boolean;
  letterSpacing: number;
  rotation: number;
  fontFamily: string;
  outlineWidth: number;
  outlineColor: string;
  shadowDepth: number;
  shadowColor: string;
  shadowOpacity: number;
  glow: boolean;
  backgroundEnabled: boolean;
  backgroundColor: string;
  backgroundOpacity: number;
  backgroundPadding: number;
  animation: Animation;
  showMode: "always" | "start" | "end";
  showSeconds: number;
};

/** size: % da altura (topo/inferior) ou da largura (esquerda/direita). */
export type Edge = { enabled: boolean; size: number; color: string };
export type EdgeKey = "top" | "bottom" | "left" | "right";
export type Frame = {
  top: Edge;
  bottom: Edge;
  left: Edge;
  right: Edge;
  color2: string;        // cor da linha interna (borda de 2 cores)
  innerPercent: number;  // espessura da linha interna, % de cada borda (0 = desliga)
};
export const EDGES: { key: EdgeKey; label: string; max: number }[] = [
  { key: "top", label: "Topo", max: 45 },
  { key: "bottom", label: "Inferior", max: 45 },
  { key: "left", label: "Esquerda", max: 45 },
  { key: "right", label: "Direita", max: 45 },
];

export type CaptionStyle = {
  fontFamily: string;
  fontSize: number;
  color: string;
  highlightColor: string;
  outlineColor: string;
  outlineWidth: number;
  y: number;
  uppercase: boolean;
  wordsPerLine: number;
  animation: "none" | "pop";
};

export type ProgressBar = { enabled: boolean; color: string; heightPercent: number; position: "top" | "bottom" };

export type TemplateConfig = {
  aspectRatio: string;
  width: number;
  height: number;
  fitMode: "cover" | "contain" | "blur";
  videoZoom: number;
  backgroundColor: string;
  accentColor: string;
  layoutPreset: string;
  vignette: boolean;
  frame: Frame;
  captions: CaptionStyle;
  progressBar: ProgressBar;
  layers: Layer[];
};

export type Template = {
  id: string;
  name: string;
  config: TemplateConfig;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type Preset = { key: string; name: string; category: string; description: string; config: TemplateConfig };
export type FontInfo = { key: string; label: string; family: string; group: string };
export type TemplateOptions = { fonts: FontInfo[]; variables: Record<string, string> };

export const MAX_LAYERS = 10;

export const ASPECTS = [
  { value: "9:16", width: 1080, height: 1920, hint: "TikTok · Reels · Shorts" },
  { value: "4:5", width: 1080, height: 1350, hint: "Feed vertical" },
  { value: "1:1", width: 1080, height: 1080, hint: "Instagram · Facebook" },
  { value: "16:9", width: 1920, height: 1080, hint: "YouTube" },
];

export const ANIMATIONS: { value: Animation; label: string }[] = [
  { value: "none", label: "Nenhuma" },
  { value: "fade", label: "Aparecer (fade)" },
  { value: "pop", label: "Pop" },
  { value: "zoom-in", label: "Zoom de entrada" },
  { value: "slide-up", label: "Subir" },
  { value: "slide-down", label: "Descer" },
  { value: "slide-left", label: "Entrar pela direita" },
  { value: "typewriter", label: "Máquina de escrever" },
  { value: "pulse", label: "Pulsar (o clipe todo)" },
];

// valores de exemplo para a prévia (mesmos do backend: SAMPLE_CONTEXT)
export const SAMPLE_VARS: Record<string, string> = {
  titulo: "Meu deus que clutch",
  gancho: "Ninguém acreditou nisso!",
  jogo: "Valorant",
  numero: "1",
  total: "8",
  nota: "94",
  projeto: "Live de sexta",
  data: new Date().toLocaleDateString("pt-BR"),
};

export function fillVars(text: string, vars: Record<string, string> = SAMPLE_VARS): string {
  return text
    .replace(/\{(\w+)\}/g, (m, k: string) => (k.toLowerCase() in vars ? vars[k.toLowerCase()] : m))
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

export function newId(): string {
  return `layer-${Math.random().toString(36).slice(2, 9)}`;
}

export function defaultLayer(kind: LayerKind, accent: string): Layer {
  return {
    id: newId(),
    kind,
    text: kind === "title" ? "{titulo}" : kind === "tag" ? "{jogo}" : "Seu texto aqui",
    x: 50,
    y: kind === "title" ? 14 : kind === "tag" ? 21 : 50,
    boxWidth: 84,
    fontSize: kind === "title" ? 64 : kind === "tag" ? 30 : 40,
    color: kind === "tag" ? accent : "#FFFFFF",
    opacity: 100,
    align: "center",
    bold: false,
    italic: false,
    uppercase: kind !== "text",
    letterSpacing: kind === "tag" ? 4 : 0,
    rotation: 0,
    fontFamily: kind === "title" ? "anton" : kind === "tag" ? "russo" : "sans",
    outlineWidth: kind === "title" ? 4 : 0,
    outlineColor: "#000000",
    shadowDepth: 0,
    shadowColor: "#000000",
    shadowOpacity: 60,
    glow: false,
    backgroundEnabled: false,
    backgroundColor: "#000000",
    backgroundOpacity: 100,
    backgroundPadding: 12,
    animation: kind === "title" ? "pop" : "none",
    showMode: "always",
    showSeconds: 3,
  };
}

export function blankConfig(): TemplateConfig {
  return {
    aspectRatio: "9:16",
    width: 1080,
    height: 1920,
    fitMode: "cover",
    videoZoom: 100,
    backgroundColor: "#111111",
    accentColor: "#FACC15",
    layoutPreset: "free",
    vignette: false,
    frame: {
      top: { enabled: false, size: 10, color: "#FACC15" },
      bottom: { enabled: false, size: 8, color: "#FACC15" },
      left: { enabled: false, size: 3, color: "#FACC15" },
      right: { enabled: false, size: 3, color: "#FACC15" },
      color2: "#000000", innerPercent: 0,
    },
    captions: {
      fontFamily: "anton", fontSize: 84, color: "#FFFFFF", highlightColor: "#FACC15", outlineColor: "#000000",
      outlineWidth: 5, y: 72, uppercase: true, wordsPerLine: 3, animation: "pop",
    },
    progressBar: { enabled: false, color: "#FACC15", heightPercent: 0.8, position: "bottom" },
    layers: [{ ...defaultLayer("title", "#FACC15"), y: 13 }],
  };
}

// ---------------------------------------------------------------- CSS (prévia no editor)
export function rgba(hex: string, opacity = 100): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(100, opacity)) / 100})`;
}

/** px do template -> unidade relativa à largura do canvas (cqw). */
export function cq(px: number, width: number): string {
  return `${(px / Math.max(1, width)) * 100}cqw`;
}

export function layerPosition(l: Layer): CSSProperties {
  const tx = l.align === "left" ? "0" : l.align === "right" ? "-100%" : "-50%";
  return {
    position: "absolute",
    left: `${l.x}%`,
    top: `${l.y}%`,
    maxWidth: `${l.boxWidth}%`,
    width: "max-content",
    transform: `translate(${tx}, -50%) rotate(${l.rotation}deg)`,
    transformOrigin: l.align === "left" ? "left center" : l.align === "right" ? "right center" : "center",
    textAlign: l.align,
  };
}

export function layerTextStyle(l: Layer, fontFamily: string, W: number): CSSProperties {
  const shadows: string[] = [];
  if (l.shadowDepth > 0) {
    shadows.push(`${cq(l.shadowDepth, W)} ${cq(l.shadowDepth, W)} 0 ${rgba(l.shadowColor, (l.shadowOpacity * l.opacity) / 100)}`);
  }
  const glow = l.glow && !l.backgroundEnabled;
  if (glow) {
    const c = rgba(l.outlineColor, l.opacity);
    shadows.push(`0 0 ${cq(10, W)} ${c}`, `0 0 ${cq(20, W)} ${c}`);
  }
  const outline = l.backgroundEnabled ? 0 : glow ? Math.max(l.outlineWidth, 4) : l.outlineWidth;
  const style: CSSProperties = {
    fontFamily: `"${fontFamily}", sans-serif`,
    fontSize: cq(l.fontSize, W),
    fontWeight: l.bold ? 700 : 400,
    fontStyle: l.italic ? "italic" : "normal",
    textTransform: l.uppercase ? "uppercase" : "none",
    letterSpacing: cq(l.letterSpacing, W),
    color: rgba(l.color, l.opacity),
    lineHeight: 1.15,
    whiteSpace: "pre-wrap",
    overflowWrap: "break-word",
    textShadow: shadows.join(", ") || undefined,
    paintOrder: "stroke fill",
  };
  if (outline > 0) {
    (style as Record<string, unknown>).WebkitTextStroke = `${cq(outline * 2, W)} ${rgba(l.outlineColor, l.opacity)}`;
  }
  if (l.backgroundEnabled) {
    Object.assign(style, {
      background: rgba(l.backgroundColor, l.backgroundOpacity),
      padding: cq(l.backgroundPadding, W),
      boxDecorationBreak: "clone",
      WebkitBoxDecorationBreak: "clone",
    });
  }
  return style;
}

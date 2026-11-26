// Em produção o site é servido pela própria API (mesma origem) => URL vazia.
// Em desenvolvimento (`npm run dev`) aponta para a API local, ver .env.development.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type Clip = {
  id: string;
  start_s: number;
  end_s: number;
  score: number;
  title: string;
  hook: string;
  reason: string;
  render_status: "pending" | "ready" | "failed";
  ranker: Ranker;
  video_url: string | null;
  download_url?: string | null;
  cuts?: number[][];
  thumb_url: string | null;
};

export type Ranker = "heuristic" | "ollama" | "claude";

export type Capabilities = {
  default_ranker: Ranker;
  default_render_height: number;
  claude_configured: boolean;
  ollama: { online: boolean; model: string; model_ready: boolean };
};

export const RANKER_LABEL: Record<Ranker, string> = {
  heuristic: "Sinais",
  ollama: "IA local",
  claude: "Claude",
};

export type ProjectSettings = {
  clip_min_s: number;
  clip_max_s: number;
  max_clips: number;
  language: string | null;
  layout: "crop" | "fit" | "split";
  facecam: { x: number; y: number; w: number; h: number } | null;
  game: string;
  captions: boolean;
  ranker: Ranker | null;
  template_id?: string | null;
  mode?: "clips" | "download";
  skip_ads?: boolean;
  download_height?: number;
  render_height?: number | null;
};

export type Project = {
  id: string;
  title: string;
  source_type: "upload" | "url";
  source_url: string | null;
  duration_s: number | null;
  status: "queued" | "processing" | "paused" | "cancelled" | "ready" | "failed";
  control: "run" | "pause" | "cancel";
  source_file_url: string | null;
  skip_segments?: { start: number; end: number; category: string; reason: string; source: string }[];
  stage: string;
  progress: number;
  error: string | null;
  settings: ProjectSettings;
  created_at: string;
  clips: Clip[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const TOKEN_KEY = "ezt_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage indisponível */
  }
}

export function fileUrl(path: string | null): string | undefined {
  return path ? `${API_URL}${path}` : undefined;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch {
      /* corpo não-JSON */
    }
    if (res.status === 401) {
      setToken(null);
      // estava logado (celular) e a sessão caiu: volta para a senha com o motivo
      if (token && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        try { sessionStorage.setItem("ezt-login-msg", msg); } catch { /* ignora */ }
        window.location.href = "/login";
      }
    }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const h = Math.floor(m / 60);
  const mm = String(m % 60).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

// qualidade do vídeo final (lado maior em px) — espelha RENDER_QUALITIES do backend
export const RENDER_QUALITIES: { value: number; label: string }[] = [
  { value: 640, label: "360p · rascunho, muito rápido" },
  { value: 854, label: "480p · rápido" },
  { value: 1280, label: "720p · HD" },
  { value: 1920, label: "1080p · Full HD (recomendado)" },
  { value: 2560, label: "1440p · 2K" },
  { value: 3840, label: "2160p · 4K (lento)" },
];

// qualidade máxima ao baixar de um link (0 = a melhor disponível)
export const DOWNLOAD_QUALITIES: { value: number; label: string }[] = [
  { value: 0, label: "Melhor disponível" },
  { value: 2160, label: "Até 4K (2160p)" },
  { value: 1440, label: "Até 2K (1440p)" },
  { value: 1080, label: "Até 1080p" },
  { value: 720, label: "Até 720p" },
  { value: 480, label: "Até 480p" },
  { value: 360, label: "Até 360p" },
];

export const isBusy = (p: Pick<Project, "status">) =>
  p.status === "queued" || p.status === "processing" || p.status === "paused";

export type SystemInfo = {
  version: string;
  can_update: boolean;
  can_restart: boolean;
  is_local: boolean;
  lan: LanInfo;
};

export type LanDevice = { ip: string; device: string; seconds_ago: number };
export type LanInfo = {
  enabled: boolean;
  configurable: boolean;
  password_set: boolean;
  urls: string[]; // o 1º é o endereço principal (vai no QR)
  restart_required: boolean;
  devices: LanDevice[];
};

export type UpdateInfo = {
  current: string;
  latest?: string;
  available: boolean;
  notes?: string;
  page?: string;
  error?: string;
  status: "idle" | "downloading" | "installing" | "error";
  progress: number;
  can_install: boolean;
};

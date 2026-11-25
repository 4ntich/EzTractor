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
  thumb_url: string | null;
};

export type Ranker = "heuristic" | "ollama" | "claude";

export type Capabilities = {
  default_ranker: Ranker;
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
};

export type Project = {
  id: string;
  title: string;
  source_type: "upload" | "url";
  source_url: string | null;
  duration_s: number | null;
  status: "queued" | "processing" | "ready" | "failed";
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
    if (res.status === 401) setToken(null);
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

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Logo from "@/components/Logo";
import ThemeSwitcher from "@/components/ThemeSwitcher";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { // motivo de ter caído aqui (ex.: conexão encerrada no computador)
    try {
      const m = sessionStorage.getItem("ezt-login-msg");
      if (m) { setError(m); sessionStorage.removeItem("ezt-login-msg"); }
    } catch { /* ignora */ }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { token } = await api<{ token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setToken(token);
      router.push("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="fixed right-4 top-4"><ThemeSwitcher /></div>
      <form onSubmit={submit} className="card ezt-rise w-full max-w-sm space-y-5 p-7">
        <div className="flex justify-center"><Logo size="lg" /></div>
        <div>
          <label className="label" htmlFor="password">Senha</label>
          <input id="password" type="password" required autoFocus className="input" value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p className="rounded-lg bg-red-950 px-3 py-2 text-sm text-red-300">{error}</p>}
        <button className="btn w-full" disabled={busy}>{busy ? "Entrando…" : "Entrar"}</button>
      </form>
    </main>
  );
}

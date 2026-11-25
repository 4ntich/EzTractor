"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Logo from "@/components/Logo";
import ThemeSwitcher from "@/components/ThemeSwitcher";
import { api, getToken, setToken } from "@/lib/api";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname() ?? "";
  const [ready, setReady] = useState(false);
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    api<{ password_required: boolean }>("/auth/status")
      .then(({ password_required }) => {
        setLocked(password_required);
        if (password_required && !getToken()) router.replace("/login");
        else setReady(true);
      })
      .catch(() => setReady(true)); // a própria página mostrará o erro de conexão
  }, [router]);

  return (
    <>
      <header className="glass-bar">
        <nav className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-2 sm:gap-6">
            <Link href="/app" aria-label="EzTractor — início"><Logo /></Link>
            <div className="flex items-center gap-1">
              <Link href="/app" className="nav-link" data-active={!path.startsWith("/app/templates")}>Projetos</Link>
              <Link href="/app/templates" className="nav-link" data-active={path.startsWith("/app/templates")}>Templates</Link>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ThemeSwitcher />
            {locked && (
              <button
                className="btn-ghost h-9 px-3 text-xs"
                onClick={() => {
                  setToken(null);
                  router.push("/login");
                }}
              >
                Sair
              </button>
            )}
          </div>
        </nav>
      </header>
      <main className="ezt-rise mx-auto max-w-6xl px-4 py-8 sm:px-6">{ready ? children : null}</main>
    </>
  );
}

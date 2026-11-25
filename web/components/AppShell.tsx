"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, getToken, setToken } from "@/lib/api";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
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
      <div className="border-b border-zinc-800">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <Link href="/app" className="text-lg font-black">
            Ez<span className="text-brand">Tractor</span>
          </Link>
          {locked && (
            <button
              className="text-sm text-zinc-400 hover:text-zinc-100"
              onClick={() => {
                setToken(null);
                router.push("/login");
              }}
            >
              Sair
            </button>
          )}
        </nav>
      </div>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{ready ? children : null}</main>
    </>
  );
}

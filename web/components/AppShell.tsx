"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, getToken, Me, setToken } from "@/lib/api";

const MeContext = createContext<{ me: Me | null; refresh: () => void }>({ me: null, refresh: () => {} });
export const useMe = () => useContext(MeContext);

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  const refresh = useCallback(() => {
    api<Me>("/me")
      .then(setMe)
      .catch(() => router.replace("/login"));
  }, [router]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    refresh();
  }, [refresh, router]);

  return (
    <MeContext.Provider value={{ me, refresh }}>
      <div className="border-b border-zinc-800">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <Link href="/app" className="text-lg font-black">
            Ez<span className="text-brand">Tractor</span>
          </Link>
          <div className="flex items-center gap-3 text-sm">
            {me && (
              <>
                <span className="rounded-full bg-zinc-800 px-3 py-1 text-xs">
                  <b className="text-brand">{me.credits}</b> créditos · plano {me.plan}
                </span>
                <span className="hidden text-zinc-400 sm:inline">{me.email}</span>
              </>
            )}
            <button
              className="text-zinc-400 hover:text-zinc-100"
              onClick={() => {
                setToken(null);
                router.push("/login");
              }}
            >
              Sair
            </button>
          </div>
        </nav>
      </div>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
    </MeContext.Provider>
  );
}

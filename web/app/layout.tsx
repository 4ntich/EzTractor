import type { Metadata } from "next";

import { THEME_BOOT_SCRIPT } from "@/lib/theme";

import "./globals.css";
import "./fonts.css";

export const metadata: Metadata = {
  title: "EzTractor",
  description: "Transforme suas lives de jogos em clipes verticais prontos para TikTok, Reels e Shorts.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" data-theme="aero" data-mode="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

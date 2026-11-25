import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EzTractor",
  description: "Transforme suas lives de jogos em clipes verticais prontos para TikTok, Reels e Shorts.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { AuthProvider } from "@/hooks/useAuth";
import "./globals.css";

export const metadata: Metadata = {
  title: "NextBot AI — Agentic Commerce Platform",
  description: "Omnichannel e-commerce run by a Supervisor Agent, 11 specialised AI agents and 12 business plugins.",
  manifest: "/manifest.webmanifest",
  applicationName: "NextBot AI",
  appleWebApp: { capable: true, title: "NextBot", statusBarStyle: "black-translucent" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = { themeColor: "#4f46e5", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}

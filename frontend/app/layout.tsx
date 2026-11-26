import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthProvider } from "@/hooks/useAuth";
import "./globals.css";

export const metadata: Metadata = {
  title: "NextBot AI — Agentic Commerce Platform",
  description: "Omnichannel e-commerce run by a Supervisor Agent, 11 specialised AI agents and 12 business plugins.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}

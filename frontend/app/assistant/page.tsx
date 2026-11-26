"use client";

import { AppShell } from "@/components/AppShell";
import { ChatPanel } from "@/components/ChatPanel";
import { useAuth } from "@/hooks/useAuth";

export default function AssistantPage() {
  const { hasRole } = useAuth();
  return (
    <AppShell>
      <ChatPanel staff={hasRole("ADMIN", "INVENTORY_MANAGER", "SUPPORT_AGENT")} />
    </AppShell>
  );
}

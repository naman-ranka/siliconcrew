"use client";

import { Launcher } from "@/components/launcher/Launcher";
import { SettingsModal } from "@/components/settings/SettingsModal";

/**
 * `/` — the Launcher (S2). The front door: workspace cards, groups, search,
 * the thread drawer and the create modal. The legacy chat page (old Sidebar +
 * fixed-tab ArtifactsPanel) is gone; opening a workspace routes to /w/{id}.
 */
export default function Home() {
  return (
    <main className="h-screen w-screen overflow-hidden">
      <Launcher />
      {/* Settings (BYOK API Keys) — shared store-driven modal. */}
      <SettingsModal />
    </main>
  );
}

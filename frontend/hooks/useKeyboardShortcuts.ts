"use client";

import { useEffect, useCallback } from "react";
import { useStore } from "@/lib/store";

export function useKeyboardShortcuts() {
  const { toggleSidebar, toggleArtifacts, sendMessage } = useStore();

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const isMac = (navigator as Navigator & { userAgentData?: { platform: string } }).userAgentData?.platform
        ? (navigator as Navigator & { userAgentData?: { platform: string } }).userAgentData!.platform.toUpperCase().includes("MAC")
        : navigator.platform.toUpperCase().includes("MAC");
      const cmdKey = isMac ? e.metaKey : e.ctrlKey;

      // Don't trigger shortcuts when typing in input
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        // Allow Escape to blur
        if (e.key === "Escape") {
          target.blur();
        }
        return;
      }

      // Cmd/Ctrl + B: Toggle sidebar
      if (cmdKey && e.key === "b") {
        e.preventDefault();
        toggleSidebar();
      }

      // Cmd/Ctrl + ]: Toggle artifacts panel
      if (cmdKey && e.key === "]") {
        e.preventDefault();
        toggleArtifacts();
      }

      // Cmd/Ctrl + K: Focus chat input
      if (cmdKey && e.key === "k") {
        e.preventDefault();
        const chatInput = document.querySelector(
          'textarea[placeholder*="Design"]'
        ) as HTMLTextAreaElement;
        chatInput?.focus();
      }

      // Escape: Clear focus / close panels
      if (e.key === "Escape") {
        const { artifactsVisible, toggleArtifacts } = useStore.getState();
        if (artifactsVisible) {
          toggleArtifacts();
        }
      }
    },
    [toggleSidebar, toggleArtifacts]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}

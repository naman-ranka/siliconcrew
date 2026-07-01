"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@/lib/auth";
import { getApiBase } from "@/lib/runtime-config";
import { useStore } from "@/lib/store";

const PENDING_EXTERNAL_AUTH_ID = "sc-mcp-external-auth-id";

export function McpConnectBridge() {
  const { enabled, status, token } = useAuth();
  const completionStarted = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const externalAuthId = url.searchParams.get("external_auth_id");
    if (!externalAuthId) return;

    try {
      sessionStorage.setItem(PENDING_EXTERNAL_AUTH_ID, externalAuthId);
    } catch {
      /* ignore */
    }
    url.searchParams.delete("external_auth_id");
    window.history.replaceState({}, "", url.toString());
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    let externalAuthId: string | null = null;
    try {
      externalAuthId = sessionStorage.getItem(PENDING_EXTERNAL_AUTH_ID);
    } catch {
      externalAuthId = null;
    }
    if (!externalAuthId || completionStarted.current) return;

    if (!enabled) {
      try {
        useStore.getState().pushToast({
          kind: "error",
          title: "MCP connection failed",
          detail: "Sign-in is not configured for this SiliconCrew deployment.",
        });
        sessionStorage.removeItem(PENDING_EXTERNAL_AUTH_ID);
      } catch {
        /* ignore */
      }
      return;
    }

    if (status === "loading") return;

    if (status !== "signed_in" || !token) return;

    completionStarted.current = true;
    fetch(`${getApiBase()}/api/mcp/oauth/complete`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ external_auth_id: externalAuthId }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          const detail = body?.detail?.message || body?.detail || response.statusText;
          throw new Error(String(detail));
        }
        return response.json() as Promise<{ redirect_uri: string }>;
      })
      .then(({ redirect_uri }) => {
        try {
          sessionStorage.removeItem(PENDING_EXTERNAL_AUTH_ID);
        } catch {
          /* ignore */
        }
        window.location.assign(redirect_uri);
      })
      .catch((err) => {
        completionStarted.current = false;
        try {
          sessionStorage.removeItem(PENDING_EXTERNAL_AUTH_ID);
          useStore.getState().pushToast({
            kind: "error",
            title: "MCP connection failed",
            detail: err instanceof Error ? err.message : String(err),
          });
        } catch {
          /* ignore */
        }
      });
  }, [enabled, status, token]);

  return null;
}

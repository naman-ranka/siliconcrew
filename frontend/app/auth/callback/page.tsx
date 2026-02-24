"use client";

import { useEffect, useState } from "react";

export default function AuthCallbackPage() {
  const [message, setMessage] = useState("Completing sign-in...");

  useEffect(() => {
    const run = async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const provider = params.get("provider");
        const code = params.get("code");
        const state = params.get("state");
        const oauthError = params.get("error");

        if (oauthError) {
          throw new Error(oauthError);
        }
        if (!provider || !code || !state) {
          throw new Error("Missing OAuth callback parameters");
        }

        const resp = await fetch(`/api/auth/callback/${provider}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, state }),
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: "OAuth callback failed" }));
          throw new Error(err.detail || "OAuth callback failed");
        }

        setMessage("Connected successfully. You can close this window.");
        if (window.opener) {
          window.opener.postMessage({ type: "oauth_complete", provider, success: true }, window.location.origin);
        }
      } catch (err) {
        const text = err instanceof Error ? err.message : "OAuth callback failed";
        setMessage(`Connection failed: ${text}`);
        if (window.opener) {
          window.opener.postMessage({ type: "oauth_complete", success: false, error: text }, window.location.origin);
        }
      } finally {
        // Give users a moment to read status, then close popup if possible.
        setTimeout(() => {
          if (window.opener) window.close();
        }, 1200);
      }
    };
    run();
  }, []);

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-md w-full rounded-lg border border-border bg-surface-1 p-6 text-center">
        <h1 className="text-lg font-semibold mb-2">Provider Connection</h1>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
    </main>
  );
}


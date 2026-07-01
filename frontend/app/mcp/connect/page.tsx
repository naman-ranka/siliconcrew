"use client";

import { Loader2, LogIn } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";

export default function McpConnectPage() {
  const { enabled, status, signIn } = useAuth();
  const needsSignIn = enabled && status === "anonymous";

  return (
    <main className="grid min-h-screen place-items-center bg-background text-foreground">
      <div className="flex min-w-72 flex-col items-center gap-4 text-center">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          {needsSignIn ? (
            <LogIn className="h-4 w-4" />
          ) : (
            <Loader2 className="h-4 w-4 animate-spin" />
          )}
          <span>{needsSignIn ? "Sign in to connect SiliconCrew" : "Connecting SiliconCrew"}</span>
        </div>
        {needsSignIn ? (
          <Button type="button" onClick={signIn} className="gap-2">
            <LogIn className="h-4 w-4" />
            Sign in
          </Button>
        ) : null}
      </div>
    </main>
  );
}

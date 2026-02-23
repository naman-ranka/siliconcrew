"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2, Key, Check } from "lucide-react";

interface AuthProfile {
  provider: string;
  profile_id: string;
  type: string;
  is_active: boolean;
  updated_at: string;
}

export function AuthSettings() {
  const [profiles, setProfiles] = useState<AuthProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [selectedProvider, setSelectedProvider] = useState("openai");

  const loadProfiles = async () => {
    setLoading(true);
    try {
        const res = await fetch("/api/settings/auth/profiles");
        if (res.ok) {
            const data = await res.json();
            setProfiles(data);
        }
    } catch (e) {
        console.error(e);
    } finally {
        setLoading(false);
    }
  };

  useEffect(() => {
    loadProfiles();
  }, []);

  const handleAddKey = async () => {
    if (!newKey.trim()) return;

    try {
        await fetch("/api/settings/auth/profiles", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                provider: selectedProvider,
                key: newKey.trim(),
                profile_id: "default"
            })
        });
        setNewKey("");
        loadProfiles();
    } catch (e) {
        console.error(e);
    }
  };

  const handleOAuthConnect = async (provider: string) => {
    try {
        // Construct callback URL (current page + special route ideally, but here we assume handling)
        // For simplicity, we redirect to a popup handler or same page
        const redirectUri = window.location.origin + "/auth/callback?provider=" + provider;

        const res = await fetch(`/api/auth/login/${provider}?redirect_uri=${encodeURIComponent(redirectUri)}`);
        if (res.ok) {
            const data = await res.json();
            // Open popup
            const width = 600;
            const height = 700;
            const left = window.screen.width / 2 - width / 2;
            const top = window.screen.height / 2 - height / 2;
            window.open(
                data.url,
                `Connect ${provider}`,
                `width=${width},height=${height},left=${left},top=${top}`
            );

            // In a real app, we'd listen for postMessage from the popup
            // For now, we assume user manually refreshes or we poll
        }
    } catch (e) {
        console.error(e);
    }
  };

  return (
    <div className="space-y-6">
        <div>
            <h3 className="text-sm font-medium mb-3">Connected Providers</h3>
            {loading ? (
                <div className="text-xs text-muted-foreground">Loading...</div>
            ) : profiles.length === 0 ? (
                <div className="text-xs text-muted-foreground italic">No providers connected.</div>
            ) : (
                <div className="space-y-2">
                    {profiles.map((p, i) => (
                        <div key={i} className="flex items-center justify-between p-2 rounded bg-surface-2 border border-border">
                            <div className="flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-green-500" />
                                <span className="capitalize font-medium">{p.provider}</span>
                                <span className="text-xs text-muted-foreground">({p.type})</span>
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {new Date(p.updated_at).toLocaleDateString()}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>

        <div className="border-t border-border pt-4">
            <h3 className="text-sm font-medium mb-3">Add Connection</h3>
            <div className="grid gap-3">
                <div className="flex gap-2">
                    <select
                        className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1"
                        value={selectedProvider}
                        onChange={(e) => setSelectedProvider(e.target.value)}
                    >
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic</option>
                        <option value="gemini">Google Gemini</option>
                    </select>
                </div>

                {selectedProvider === "gemini" ? (
                    <div className="flex flex-col gap-2">
                        <Button variant="outline" onClick={() => handleOAuthConnect("google")}>
                            <Key className="h-4 w-4 mr-2" />
                            Connect with Google
                        </Button>
                        <div className="relative flex justify-center text-xs uppercase">
                            <span className="bg-surface-1 px-2 text-muted-foreground">Or using API Key</span>
                        </div>
                    </div>
                ) : null}

                <Input
                    type="password"
                    placeholder="API Key (sk-...)"
                    value={newKey}
                    onChange={(e) => setNewKey(e.target.value)}
                    className="bg-surface-2"
                />
                <Button onClick={handleAddKey} disabled={!newKey.trim()}>
                    <Plus className="h-4 w-4 mr-2" />
                    Connect
                </Button>
            </div>
        </div>
    </div>
  );
}

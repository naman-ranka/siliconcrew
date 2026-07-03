"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Cpu,
  Download,
  ExternalLink,
  FilePlus2,
  Link as LinkIcon,
  Play,
  SearchCheck,
  Settings2,
} from "lucide-react";

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore, type ContextMenuState } from "@/lib/workbenchUiStore";
import { openArtifact, artifactKeyForFile } from "@/lib/openArtifact";
import { runCommand, COMMANDS } from "@/lib/commands";
import { workspaceApi } from "@/lib/api";
import { isSynthTopFile } from "@/lib/fileTree";
import { cn } from "@/lib/utils";

const MARGIN = 8;

function MenuItem({
  onSelect,
  icon,
  label,
  kbd,
}: {
  onSelect: () => void;
  icon: React.ReactNode;
  label: string;
  kbd?: string;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onSelect}
      className={cn(
        "flex h-7 w-full items-center gap-2 px-2 text-left text-xs outline-none",
        "hover:bg-accent focus-visible:bg-accent transition-colors duration-fast ease-swift"
      )}
    >
      <span className="shrink-0 text-muted-foreground">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {kbd && (
        <kbd className="shrink-0 font-mono text-[10px] text-muted-foreground/70">{kbd}</kbd>
      )}
    </button>
  );
}

function Separator() {
  return <div className="my-1 h-px bg-border" role="separator" />;
}

/**
 * Right-click menu for file rows in the FileExplorer. Rendered from the
 * ephemeral `contextMenu` UI-store slot; fixed-positioned at the click point,
 * clamped to the viewport, dismissed on outside click / Esc / scroll.
 */
export function FileContextMenu() {
  const contextMenu = useWorkbenchUiStore((s) => s.contextMenu);
  if (!contextMenu) return null;
  // Keyed remount per (position, path) so measurement/clamping state resets.
  return <Menu key={`${contextMenu.x}:${contextMenu.y}:${contextMenu.path}`} menu={contextMenu} />;
}

function Menu({ menu }: { menu: ContextMenuState }) {
  const setContextMenu = useWorkbenchUiStore((s) => s.setContextMenu);
  const setCommandModal = useWorkbenchUiStore((s) => s.setCommandModal);
  const setNewFilePrefix = useWorkbenchUiStore((s) => s.setNewFilePrefix);
  const currentSession = useStore((s) => s.currentSession);
  const manifest = useStore((s) => s.manifest);
  const pushToast = useStore((s) => s.pushToast);

  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: menu.x, y: menu.y });

  const close = () => setContextMenu(null);

  // Clamp to the viewport once we know the rendered size (before paint).
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const { innerWidth, innerHeight } = window;
    setPos({
      x: Math.max(MARGIN, Math.min(menu.x, innerWidth - el.offsetWidth - MARGIN)),
      y: Math.max(MARGIN, Math.min(menu.y, innerHeight - el.offsetHeight - MARGIN)),
    });
  }, [menu.x, menu.y]);

  // Dismiss on outside pointer-down, Esc, scroll, or resize.
  useEffect(() => {
    const onPointerDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onScroll = (e: Event) => {
      // Scrolling inside the menu itself is fine; anything else dismisses.
      if (ref.current && e.target instanceof Node && ref.current.contains(e.target)) return;
      close();
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const path = menu.path;
  const isDir = menu.kind === "dir";
  const basename = path.split("/").pop() || path;
  const isVerilog = !isDir && /\.(v|sv)$/i.test(basename);
  const isSynthTop = isVerilog && isSynthTopFile(basename, manifest);
  const sessionId = currentSession?.id ?? null;

  const doOpen = () => {
    if (sessionId) openArtifact(sessionId, artifactKeyForFile(path));
    close();
  };

  const doCopyPath = () => {
    void navigator.clipboard?.writeText(path).then(
      () => pushToast({ kind: "success", title: "Path copied", detail: path }),
      () => pushToast({ kind: "error", title: "Couldn’t copy path" })
    );
    close();
  };

  const doDownload = () => {
    if (sessionId) {
      void workspaceApi.downloadRawFile(sessionId, path).catch(() =>
        pushToast({ kind: "error", title: "Download failed", detail: basename })
      );
    }
    close();
  };

  const run = (id: "lint" | "sim" | "synth") => {
    void runCommand(id); // fire-and-forget: toasts/polling/activity handled inside
    close();
  };

  const modal = (id: "sim" | "synth") => {
    setCommandModal(id);
    close();
  };

  return (
    <div
      ref={ref}
      role="menu"
      aria-label={`Actions for ${basename}`}
      style={{ left: pos.x, top: pos.y }}
      className="fixed z-50 min-w-[192px] rounded-md border border-border bg-popover py-1 text-xs text-popover-foreground shadow-e2"
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="truncate border-b border-border px-2 pb-1 pt-0.5 font-mono text-[10px] text-muted-foreground">
        {basename}
      </div>

      {isDir ? (
        <>
          <MenuItem
            onSelect={() => {
              setNewFilePrefix(path);
              close();
            }}
            icon={<FilePlus2 className="h-3.5 w-3.5" />}
            label="New file in folder"
          />
          <MenuItem onSelect={doCopyPath} icon={<LinkIcon className="h-3.5 w-3.5" />} label="Copy path" />
        </>
      ) : (
        <>
          <MenuItem onSelect={doOpen} icon={<ExternalLink className="h-3.5 w-3.5" />} label="Open" />
          <MenuItem onSelect={doCopyPath} icon={<LinkIcon className="h-3.5 w-3.5" />} label="Copy path" />
          <MenuItem onSelect={doDownload} icon={<Download className="h-3.5 w-3.5" />} label="Download" />
        </>
      )}

      {isVerilog && (
        <>
          <Separator />
          <MenuItem
            onSelect={() => run("lint")}
            icon={<SearchCheck className="h-3.5 w-3.5" />}
            label={COMMANDS.lint.label}
            kbd={`⌘${COMMANDS.lint.shortcut}`}
          />
          <MenuItem
            onSelect={() => run("sim")}
            icon={<Play className="h-3.5 w-3.5" />}
            label={COMMANDS.sim.label}
            kbd={`⌘${COMMANDS.sim.shortcut}`}
          />
          {isSynthTop && (
            <MenuItem
              onSelect={() => run("synth")}
              icon={<Cpu className="h-3.5 w-3.5" />}
              label={COMMANDS.synth.label}
              kbd={`⌘${COMMANDS.synth.shortcut}`}
            />
          )}
          <Separator />
          <MenuItem
            onSelect={() => modal("sim")}
            icon={<Settings2 className="h-3.5 w-3.5" />}
            label="Simulate…"
          />
          {isSynthTop && (
            <MenuItem
              onSelect={() => modal("synth")}
              icon={<Settings2 className="h-3.5 w-3.5" />}
              label="Synthesize…"
            />
          )}
        </>
      )}
    </div>
  );
}

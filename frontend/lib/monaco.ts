"use client";

import { useEffect, useState } from "react";
import { loader } from "@monaco-editor/react";

export type MonacoLoadState = "loading" | "monaco" | "fallback";
export type SiliconCrewMonacoTheme = "siliconcrew-dark" | "siliconcrew-light";

type MonacoApi = Awaited<ReturnType<typeof loader.init>>;

const MONACO_VS_PATH = "/monaco/vs";
const LOAD_TIMEOUT_MS = 8000;

let configured = false;
let initPromise: Promise<MonacoApi> | null = null;
let terminalState: "idle" | "ready" | "failed" = "idle";
let themesDefined = false;

function configureLoader() {
  if (configured) return;
  loader.config({ paths: { vs: MONACO_VS_PATH } });
  configured = true;
}

function defineThemes(monaco: MonacoApi) {
  if (themesDefined) return;

  monaco.editor.defineTheme("siliconcrew-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "7FA36F", fontStyle: "italic" },
      { token: "keyword", foreground: "79A8D8" },
      { token: "number", foreground: "D6A221" },
      { token: "string", foreground: "D98B6A" },
      { token: "type", foreground: "64C2A6" },
    ],
    colors: {
      "editor.background": "#141312",
      "editor.foreground": "#e8e3dc",
      "editorGutter.background": "#141312",
      "editorLineNumber.foreground": "#7d766d",
      "editorLineNumber.activeForeground": "#d97757",
      "editorCursor.foreground": "#d97757",
      "editor.lineHighlightBackground": "#211f1c",
      "editor.selectionBackground": "#8a4f3c66",
      "editor.inactiveSelectionBackground": "#8a4f3c33",
      "editorIndentGuide.background1": "#3a352f",
      "editorIndentGuide.activeBackground1": "#6a6157",
      "editorWidget.background": "#1e1c19",
      "editorWidget.border": "#35302a",
    },
  });

  monaco.editor.defineTheme("siliconcrew-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "comment", foreground: "4f7d45", fontStyle: "italic" },
      { token: "keyword", foreground: "1f6fb2" },
      { token: "number", foreground: "8a6413" },
      { token: "string", foreground: "a34824" },
      { token: "type", foreground: "19755e" },
    ],
    colors: {
      "editor.background": "#f4efe4",
      "editor.foreground": "#302822",
      "editorGutter.background": "#f4efe4",
      "editorLineNumber.foreground": "#81766a",
      "editorLineNumber.activeForeground": "#a64728",
      "editorCursor.foreground": "#a64728",
      "editor.lineHighlightBackground": "#eee4d4",
      "editor.selectionBackground": "#d9775740",
      "editor.inactiveSelectionBackground": "#d9775724",
      "editorIndentGuide.background1": "#d7cabb",
      "editorIndentGuide.activeBackground1": "#a99a8a",
      "editorWidget.background": "#fffdf8",
      "editorWidget.border": "#d8cabc",
    },
  });

  themesDefined = true;
}

export function initMonaco(): Promise<MonacoApi> {
  configureLoader();
  if (!initPromise) {
    initPromise = loader
      .init()
      .then((monaco) => {
        defineThemes(monaco);
        terminalState = "ready";
        return monaco;
      })
      .catch((error) => {
        terminalState = "failed";
        throw error;
      });
  }
  return initPromise;
}

function currentTheme(): SiliconCrewMonacoTheme {
  if (typeof document === "undefined") return "siliconcrew-dark";
  return document.documentElement.classList.contains("light")
    ? "siliconcrew-light"
    : "siliconcrew-dark";
}

export function useMonacoThemeName(): SiliconCrewMonacoTheme {
  const [theme, setTheme] = useState<SiliconCrewMonacoTheme>(() => currentTheme());

  useEffect(() => {
    const update = () => setTheme(currentTheme());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return theme;
}

export function useMonacoLoadState(timeoutMs = LOAD_TIMEOUT_MS): MonacoLoadState {
  const [state, setState] = useState<MonacoLoadState>(() => {
    if (terminalState === "ready") return "monaco";
    if (terminalState === "failed") return "fallback";
    return "loading";
  });

  useEffect(() => {
    if (terminalState === "ready") {
      setState("monaco");
      return;
    }
    if (terminalState === "failed") {
      setState("fallback");
      return;
    }

    let cancelled = false;
    let timedOut = false;
    const timer = window.setTimeout(() => {
      timedOut = true;
      if (!cancelled && terminalState !== "ready") setState("fallback");
    }, timeoutMs);

    void initMonaco()
      .then(() => {
        if (!cancelled && !timedOut) setState("monaco");
      })
      .catch(() => {
        if (!cancelled) setState("fallback");
      });

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [timeoutMs]);

  return state;
}

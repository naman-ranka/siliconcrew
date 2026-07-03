// Pure helpers for the ⌘O session quick-switch (S3) — extracted so the
// filter/group-order/keyboard logic is unit-testable without the overlay.

import type { Project, Session } from "@/types";

export interface QuickSwitchSection {
  /** The group (backend project), or null for the trailing "Ungrouped" bucket. */
  project: Project | null;
  sessions: Session[];
}

/** Recency-first filter — the exact ordering the Launcher uses (updated_at
 * falling back to created_at, newest first), narrowed by a case-insensitive
 * substring match over the display name (falling back to the id). */
export function filterSessions(sessions: Session[], query: string): Session[] {
  const needle = query.trim().toLowerCase();
  const byRecency = [...sessions].sort((a, b) => {
    const ta = new Date(a.updated_at ?? a.created_at ?? 0).getTime();
    const tb = new Date(b.updated_at ?? b.created_at ?? 0).getTime();
    return tb - ta;
  });
  if (!needle) return byRecency;
  return byRecency.filter((s) => (s.name ?? s.id).toLowerCase().includes(needle));
}

/** Group the (already filtered) sessions: groups in the projects list's own
 * order, then an "Ungrouped" bucket last (sessions without a project, or with
 * a project the list doesn't know). Empty sections are dropped. The visual
 * order this produces IS the keyboard order — flattenSections must match. */
export function groupSessions(filtered: Session[], projects: Project[]): QuickSwitchSection[] {
  const sections: QuickSwitchSection[] = [];
  for (const project of projects) {
    const list = filtered.filter((s) => s.project_id === project.id);
    if (list.length > 0) sections.push({ project, sessions: list });
  }
  const ungrouped = filtered.filter(
    (s) => !s.project_id || !projects.some((p) => p.id === s.project_id)
  );
  if (ungrouped.length > 0) sections.push({ project: null, sessions: ungrouped });
  return sections;
}

/** The flat keyboard order: sections top-to-bottom, rows within each. */
export function flattenSections(sections: QuickSwitchSection[]): Session[] {
  return sections.flatMap((section) => section.sessions);
}

/** ↑/↓ highlight movement — clamps at both ends (no wrap, per the prototype). */
export function moveHighlight(index: number, delta: number, length: number): number {
  if (length <= 0) return 0;
  return Math.min(Math.max(index + delta, 0), length - 1);
}

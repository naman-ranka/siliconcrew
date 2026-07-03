// Tiny shared helpers for the launcher surfaces.

export const plural = (n: number, w: string): string => `${n} ${w}${n === 1 ? "" : "s"}`;

// Stable group swatch — indexed by the group's position in the projects list,
// so a group keeps its color across views without persisting anything.
export const GROUP_SWATCH = [
  "hsl(14 63% 60%)",
  "hsl(210 47% 61%)",
  "hsl(136 49% 49%)",
  "hsl(43 73% 49%)",
  "hsl(280 42% 63%)",
];

export const groupSwatch = (index: number): string =>
  GROUP_SWATCH[(index < 0 ? 0 : index) % GROUP_SWATCH.length];

/** Workspace-dir slug for a session name (mirrors the prototype). */
export const slugify = (x: string): string =>
  x
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");

"use client";

import { SkillsPage } from "@/components/skills/SkillsPage";

/**
 * `/skills` — the user-editable half of the skill store. A page rather than a
 * modal because the work here is reading and writing markdown, and a dialog
 * that has to hold an editor has already stopped being a dialog.
 */
export default function Skills() {
  return <SkillsPage />;
}

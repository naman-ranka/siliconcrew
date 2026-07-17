// The create-workspace action, extracted from CreateSessionModal's submit so
// the post-sign-in intent replay (E2) re-runs EXACTLY the same logic —
// including group resolution and its 409 re-match — instead of duplicating
// it. Pure module (no hooks): reads store state via getState, so both the
// modal and the Launcher's replay effect can call it.

import { useStore } from "@/lib/store";
import { useWorkbenchUiStore } from "@/lib/workbenchUiStore";
import type { ViewMode } from "@/lib/nav";
import { slugify } from "./util";

export interface CreateSessionInput {
  /** Raw user-typed name (slugified here, same as the modal preview). */
  name: string;
  posture: ViewMode;
  /** Raw group name; empty string = no group. */
  group: string;
}

/**
 * Resolve the group (existing by display name OR immutable slug-id; create on
 * the fly; on a 409 reload-and-re-match), create the session on the catalog
 * default model, and persist the chosen shell. Throws on failure — callers
 * own the error surface. Returns the new session id for navigation.
 */
export async function performCreate({ name, posture, group }: CreateSessionInput): Promise<string> {
  const slug = slugify(name) || "untitled";
  const { createSession, createProject } = useStore.getState();

  let projectId: string | null = null;
  const groupName = group.trim();
  if (groupName) {
    const wanted = groupName.toLowerCase();
    const wantedSlug = slugify(groupName).toLowerCase();
    const match = (list: { id: string; name: string }[]) =>
      list.find(
        (p) => p.name.toLowerCase() === wanted || p.id.toLowerCase() === wantedSlug
      );
    const existing = match(useStore.getState().projects);
    if (existing) {
      projectId = existing.id;
    } else {
      try {
        projectId = (await createProject(groupName)).id;
      } catch (err) {
        // Created elsewhere / stale list: reload and re-match instead of
        // failing the whole session creation.
        if ((err as { status?: number }).status === 409) {
          await useStore.getState().loadProjects();
          const found = match(useStore.getState().projects);
          if (!found) throw err;
          projectId = found.id;
        } else {
          throw err;
        }
      }
    }
  }

  // Model: the real catalog default (loaded by the modal / launcher);
  // sessionsApi falls back to its own default when the registry hasn't landed.
  const { defaultModel, models } = useStore.getState();
  const model = defaultModel ?? models[0]?.id ?? "gemini-3.5-flash";
  const session = await createSession(slug, model, projectId);
  useWorkbenchUiStore.getState().setShell(session.id, posture);
  return session.id;
}

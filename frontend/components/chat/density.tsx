"use client";

import { createContext, useContext } from "react";

// Container-driven chat density. The SAME ChatArea renders as a ~350px IDE
// side rail and as the full-width centered agent conversation — viewport
// breakpoints (sm:/md:) are the wrong signal for it, so ChatArea measures its
// own width and provides one boolean. Components branch on it for layout
// (avatars, button labels, grid columns); typography scales in globals.css
// via the matching [data-density="compact"] attribute.
export const CHAT_COMPACT_MAX_W = 480; // px — below this the chat is a rail

const ChatDensityContext = createContext<boolean>(false);

export const ChatDensityProvider = ChatDensityContext.Provider;

/** True when the chat container is rail-narrow (see CHAT_COMPACT_MAX_W). */
export function useChatCompact(): boolean {
  return useContext(ChatDensityContext);
}

// Vitest setup — adds jest-dom matchers (toBeVisible, toHaveTextContent, ...).
import "@testing-library/jest-dom";

// jsdom lacks ResizeObserver, which cmdk (the command palette) observes on
// mount — provide a no-op stub so those components can render under test.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// jsdom doesn't implement scrollIntoView; cmdk calls it when it auto-selects
// the first item on open.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

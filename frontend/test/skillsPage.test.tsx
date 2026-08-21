import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

/**
 * The Skills page. What is worth asserting is what the design forbids:
 *
 *  - every row says which LAYER answered for that name, so "yours" and "ours"
 *    are never confusable;
 *  - the control is on/off and nothing more — no conditions, no ordering;
 *  - the always-in-force skill is marked differently from the others, and
 *    switching it off is visible rather than quiet;
 *  - the page never decides a merge; it re-reads what the backend decided.
 */

// vi.mock is hoisted above every const in this file, so the fake's state lives
// on a lazily-created singleton the factory reaches through instead.
const fake = vi.hoisted(() => {
  const state = {
    listCalls: [] as unknown[],
    index: { skills: [] as Array<Record<string, unknown>>, unmatched_disabled: [] as string[] },
    setEnabled: vi.fn(async () => ({ ok: true as const, name: "x", enabled: false })),
    remove: vi.fn(async () => ({ ok: true as const, name: "x" })),
    save: vi.fn(async () => ({ ok: true as const, name: "my-own-thing" })),
  };
  return state;
});

vi.mock("@/lib/api", () => ({
  skillsApi: {
    list: async () => {
      fake.listCalls.push(1);
      return fake.index;
    },
    read: async (name: string) => ({
      ...fake.index.skills.find((s) => s.name === name),
      text: `---\nname: ${name}\ndescription: d\n---\n\nTEXT-OF-${name}\n`,
      // A shipped text exists for a built-in and for a replacement of one —
      // and for nothing else. That is what makes "Reset to shipped" honest.
      builtin_text: String(
        fake.index.skills.find((s) => s.name === name)?.layer ?? ""
      ).includes("builtin")
        ? "SHIPPED-TEXT"
        : null,
    }),
    save: fake.save,
    remove: fake.remove,
    setEnabled: fake.setEnabled,
  },
}));

const { setEnabled, remove, save } = fake;
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

// Auth settles asynchronously. Default to a settled state so every other test
// reads as it did before; the one test that cares drives this directly.
const auth = vi.hoisted(() => ({ status: "anonymous" as string }));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    enabled: false,
    status: auth.status,
    user: null,
    token: null,
    signIn: () => {},
    signOut: () => {},
  }),
}));

import { SkillsPage } from "@/components/skills/SkillsPage";

beforeEach(() => {
  auth.status = "anonymous";
  fake.listCalls.length = 0;
  setEnabled.mockClear();
  remove.mockClear();
  save.mockClear();
  fake.index = {
    skills: [
      {
        name: "shipped-thing",
        layer: "builtin",
        enabled: true,
        description: "A shipped procedure.",
        always_load: false,
        builtin_changed: null,
        error: null,
      },
      {
        name: "quiet-guard",
        layer: "builtin",
        enabled: true,
        description: "The one with no trigger.",
        always_load: true,
        builtin_changed: null,
        error: null,
      },
      {
        name: "my-own-thing",
        layer: "user-replaces-builtin",
        enabled: true,
        description: "Mine.",
        always_load: false,
        builtin_changed: true,
        error: null,
      },
    ],
    unmatched_disabled: [],
  };
});

describe("the Skills page", () => {
  it("says which layer answered for every name", async () => {
    render(<SkillsPage />);
    await screen.findByTestId("skill-row-shipped-thing");

    expect(screen.getAllByText("Built-in")).toHaveLength(2);
    expect(screen.getByText("Yours, replacing a built-in")).toBeTruthy();
  });

  it("offers on/off per skill and nothing more", async () => {
    render(<SkillsPage />);
    await screen.findByTestId("skill-row-shipped-thing");

    const switches = screen.getAllByRole("switch");
    expect(switches).toHaveLength(3);
    fireEvent.click(screen.getByLabelText("Disable shipped-thing"));
    await waitFor(() => expect(setEnabled).toHaveBeenCalledWith("shipped-thing", false));
    // ...and the page re-reads rather than believing its own optimism.
    await waitFor(() => expect(fake.listCalls.length).toBeGreaterThan(1));
  });

  it("marks the always-in-force skill differently from the others", async () => {
    render(<SkillsPage />);
    await screen.findByTestId("skill-row-quiet-guard");

    expect(screen.getByLabelText("Always in force")).toBeTruthy();
    expect(screen.getByText(/no trigger of its own/i)).toBeTruthy();
    expect(screen.queryByTestId("safety-net-off")).toBeNull();
  });

  it("says out loud when the always-in-force skill is off", async () => {
    fake.index.skills[1].enabled = false;
    render(<SkillsPage />);
    await screen.findByTestId("skill-row-quiet-guard");

    const banner = await screen.findByTestId("safety-net-off");
    expect(banner.textContent).toMatch(/stamped/i);
  });

  it("reports a built-in that moved without touching the replacement", async () => {
    render(<SkillsPage />);
    await screen.findByTestId("skill-row-my-own-thing");
    expect(screen.getByText(/still what runs/i)).toBeTruthy();
  });

  it("offers reset on a replacement and never on a built-in", async () => {
    render(<SkillsPage />);
    fireEvent.click(await screen.findByTestId("skill-row-my-own-thing"));
    await screen.findByText("Reset to shipped");

    fireEvent.click(screen.getByTestId("skill-row-shipped-thing"));
    await waitFor(() => expect(screen.queryByText("Reset to shipped")).toBeNull());
    expect(screen.getByText("Replace with your own")).toBeTruthy();
  });

  it("clears a switched-off name that no longer matches anything", async () => {
    fake.index.unmatched_disabled = ["a-skill-that-was-renamed"];
    render(<SkillsPage />);
    const clear = await screen.findByText(/Clear/);

    fireEvent.click(clear);
    await waitFor(() =>
      expect(setEnabled).toHaveBeenCalledWith("a-skill-that-was-renamed", true)
    );
  });

  it("names the new skill from its own frontmatter, not from a field", async () => {
    render(<SkillsPage />);
    fireEvent.click(await screen.findByText("New skill"));
    const editor = screen.getByLabelText("Skill text") as HTMLTextAreaElement;

    fireEvent.change(editor, {
      target: { value: "---\nname: my-own-thing\ndescription: d\n---\n\nbody\n" },
    });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(save).toHaveBeenCalledWith("my-own-thing", expect.any(String)));
  });

  it("refuses to save something that is not a skill file", async () => {
    render(<SkillsPage />);
    fireEvent.click(await screen.findByText("New skill"));
    fireEvent.change(screen.getByLabelText("Skill text"), { target: { value: "just prose" } });
    fireEvent.click(screen.getByText("Save"));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(save).not.toHaveBeenCalled();
  });

  it("asks nothing until it knows who is asking", async () => {
    // /api/skills answers an unidentified caller with 200 and the built-in
    // defaults — there is no 401 for the API layer to recover from. A read
    // fired while auth is still settling therefore renders ANOTHER tenant's
    // answer as yours, and the first toggle writes it back over your own.
    auth.status = "loading";
    const view = render(<SkillsPage />);

    await waitFor(() => expect(screen.getByText("Loading…")).toBeTruthy());
    expect(fake.listCalls.length).toBe(0);

    auth.status = "signed_in";
    view.rerender(<SkillsPage />);

    expect(await screen.findByText("shipped-thing")).toBeTruthy();
    expect(fake.listCalls.length).toBe(1);
  });

  it("saves a skill whose name is quoted in the frontmatter", async () => {
    // `name: "my-skill"` is valid YAML and a valid skill. Taking the name
    // straight out of the text put the quotes in the URL, so the path said
    // one thing and the document said another and the backend refused a file
    // the page had just called valid.
    render(<SkillsPage />);
    fireEvent.click(await screen.findByText("New skill"));
    fireEvent.change(screen.getByLabelText("Skill text"), {
      target: { value: '---\nname: "my-own-thing"\ndescription: d\n---\n\nbody\n' },
    });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("my-own-thing", expect.any(String))
    );
  });
});

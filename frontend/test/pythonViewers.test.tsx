import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const getFileSmart = vi.fn();
const fetchRawObjectUrl = vi.fn();

vi.mock("@/lib/api", () => ({
  projectsApi: {},
  sessionsApi: {},
  chatApi: {},
  workbenchApi: {},
  workspaceApi: {
    getFileSmart: (...a: unknown[]) => getFileSmart(...a),
    fetchRawObjectUrl: (...a: unknown[]) => fetchRawObjectUrl(...a),
    downloadRawFile: vi.fn(),
  },
}));

import { useStore } from "@/lib/store";
import { ImageArtifact } from "@/components/workbench/viewers/ImageArtifact";
import { DataArtifact, parseDelimited } from "@/components/workbench/viewers/DataArtifact";
import { TextArtifact } from "@/components/workbench/viewers/TextArtifact";

// jsdom doesn't implement object URLs; the image viewer revokes on cleanup.
globalThis.URL.createObjectURL = vi.fn(() => "blob:stub");
globalThis.URL.revokeObjectURL = vi.fn();

const SESSION = {
  id: "s1",
  name: "s1",
  model_name: "x",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

function smart(content: string | null, over: Partial<{ binary: boolean; tooLarge: boolean }> = {}) {
  return {
    filename: "f",
    content,
    size: content?.length ?? 0,
    binary: over.binary ?? false,
    tooLarge: over.tooLarge ?? false,
  };
}

beforeEach(() => {
  getFileSmart.mockReset();
  fetchRawObjectUrl.mockReset();
  useStore.setState({ currentSession: SESSION as never, fileCache: {} });
});

describe("parseDelimited (CSV/TSV)", () => {
  it("splits rows/cols and honors quoted fields with embedded delimiters", () => {
    const rows = parseDelimited('a,b,c\n1,"x,y",3\n', ",");
    expect(rows[0]).toEqual(["a", "b", "c"]);
    expect(rows[1]).toEqual(["1", "x,y", "3"]);
  });
  it("stops at the row cap", () => {
    const text = Array.from({ length: 50 }, (_, i) => `${i}`).join("\n") + "\n";
    expect(parseDelimited(text, ",", 10)).toHaveLength(10);
  });
});

describe("ImageArtifact (PA7)", () => {
  it("renders the image from an authed blob object URL", async () => {
    fetchRawObjectUrl.mockResolvedValue("blob:plot");
    render(<ImageArtifact path="out/plot.png" />);
    const img = await screen.findByRole("img");
    expect(img).toHaveAttribute("src", "blob:plot");
    expect(img).toHaveAttribute("alt", "plot.png");
    expect(fetchRawObjectUrl).toHaveBeenCalledWith("s1", "out/plot.png");
  });

  it("shows an honest error when the fetch fails", async () => {
    fetchRawObjectUrl.mockRejectedValue(new Error("HTTP 404"));
    render(<ImageArtifact path="missing.png" />);
    expect(await screen.findByText("Couldn't load image")).toBeInTheDocument();
    expect(screen.getByText("HTTP 404")).toBeInTheDocument();
  });
});

describe("DataArtifact (PA7)", () => {
  it("renders a CSV as a table", async () => {
    getFileSmart.mockResolvedValue(smart("name,val\nalpha,1\nbeta,2\n"));
    render(<DataArtifact path="vectors.csv" />);
    expect(await screen.findByTestId("data-artifact")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
    // Header cells present.
    expect(screen.getByText("name")).toBeInTheDocument();
  });

  it("caps rows and reports 'showing N of M'", async () => {
    const big = "h\n" + Array.from({ length: 900 }, (_, i) => `r${i}`).join("\n") + "\n";
    getFileSmart.mockResolvedValue(smart(big));
    render(<DataArtifact path="big.csv" />);
    await screen.findByTestId("data-artifact");
    expect(screen.getByText(/showing 500 of 900 rows/)).toBeInTheDocument();
  });

  it("pretty-prints JSON", async () => {
    getFileSmart.mockResolvedValue(smart('{"a":1,"b":[2,3]}'));
    render(<DataArtifact path="d.json" />);
    await screen.findByTestId("data-artifact");
    // Pretty output puts each key on its own indented line.
    expect(screen.getByText(/"a": 1/)).toBeInTheDocument();
  });
});

describe("TextArtifact (PA7)", () => {
  it("renders text content in a monospace block", async () => {
    getFileSmart.mockResolvedValue(smart("hello log line\nsecond line"));
    render(<TextArtifact path="run.log" />);
    expect(await screen.findByTestId("text-artifact")).toHaveTextContent("hello log line");
  });

  it("is honest about a binary file", async () => {
    getFileSmart.mockResolvedValue(smart(null, { binary: true }));
    render(<TextArtifact path="blob.bin" />);
    expect(await screen.findByText(/Binary file/)).toBeInTheDocument();
  });
});

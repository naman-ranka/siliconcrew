import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// First-message auth handshake (naman-ranka/siliconcrew-dev#59): the token
// must never appear in the WS URL (Cloud Run logs query strings verbatim);
// instead {"type":"auth","token":...} is the FIRST frame on the socket —
// before the store's own onopen handler sends the first chat message, on
// fresh connects and reconnects alike.

// Minimal fake for the global WebSocket: records the URL, ordered sends, and
// replays open to both addEventListener listeners (registration order) and a
// later-assigned `onopen` — matching the browser's dispatch order.
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  private openListeners: Array<() => void> = [];

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  addEventListener(type: string, cb: () => void) {
    if (type === "open") this.openListeners.push(cb);
  }
  send(data: string) {
    this.sent.push(data);
  }
  simulateOpen() {
    for (const cb of this.openListeners) cb();
    this.onopen?.();
  }
}

import { chatApi } from "@/lib/api";
import { setAuthTokenGetter } from "@/lib/authToken";

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  setAuthTokenGetter(() => null); // back to the unregistered (self-host) default
});

describe("chat WS auth handshake (#59)", () => {
  it("never puts the token in the URL, and sends it as the first frame", () => {
    setAuthTokenGetter(() => "jwt-secret-123");

    const ws = chatApi.createConnection("s1", "t1") as unknown as FakeWebSocket;

    expect(ws.url).toContain("/api/chat/s1");
    expect(ws.url).toContain("thread_id=t1");
    expect(ws.url).not.toContain("token");
    expect(ws.url).not.toContain("jwt-secret-123");

    // The store assigns onopen AFTER createConnection returns (lib/store.ts
    // sendMessage) — the auth frame must still beat that first chat message.
    ws.onopen = () => ws.send(JSON.stringify({ message: "hi", thread_id: "t1" }));
    ws.simulateOpen();

    expect(ws.sent.length).toBe(2);
    expect(JSON.parse(ws.sent[0])).toEqual({ type: "auth", token: "jwt-secret-123" });
    expect(JSON.parse(ws.sent[1]).message).toBe("hi");
  });

  it("signed-out / self-host sends an auth frame with a null token", () => {
    const ws = chatApi.createConnection("s1") as unknown as FakeWebSocket;
    ws.simulateOpen();
    expect(JSON.parse(ws.sent[0])).toEqual({ type: "auth", token: null });
    expect(ws.url).not.toContain("token");
  });

  it("reconnects read the token at open time (a refreshed token is used)", () => {
    let token = "stale-token";
    setAuthTokenGetter(() => token);

    const first = chatApi.createConnection("s1", "t1") as unknown as FakeWebSocket;
    first.simulateOpen();
    expect(JSON.parse(first.sent[0]).token).toBe("stale-token");

    token = "fresh-token";
    const second = chatApi.createConnection("s1", "t1") as unknown as FakeWebSocket;
    second.simulateOpen();
    expect(JSON.parse(second.sent[0]).token).toBe("fresh-token");
  });
});

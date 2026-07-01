// TEST-ONLY local WebSocket relay: browser → ws://localhost:8092 → wss://deployed.
// The sandboxed headless browser can't open a WSS to Cloud Run (agent proxy
// doesn't tunnel WebSockets), but node connects directly fine. This bridges the
// browser (localhost, no-proxy) to the deployed chat WS so the chatbot UI is
// testable end to end. Forwards path+query (incl. ?token=) verbatim.
import { createRequire } from "module";
import http from "http";
const require = createRequire("/home/user/siliconcrew/frontend/");
const { WebSocketServer, WebSocket } = require("ws");

const BACKEND = "wss://siliconcrew-backend-psp2dkllmq-uc.a.run.app";
const PORT = 8092;

const server = http.createServer();
const wss = new WebSocketServer({ server });

wss.on("connection", (client, req) => {
  const target = BACKEND + req.url; // /api/chat/<id>?token=...&thread_id=...
  console.log("client→relay:", req.url.replace(/token=[^&]+/, "token=REDACTED"));
  const upstream = new WebSocket(target);
  const queue = [];
  upstream.on("open", () => { for (const [d, b] of queue) upstream.send(d, { binary: b }); queue.length = 0; });
  client.on("message", (d, isBinary) => { if (upstream.readyState === 1) upstream.send(d, { binary: isBinary }); else queue.push([d, isBinary]); });
  upstream.on("message", (d, isBinary) => { if (client.readyState === 1) client.send(d, { binary: isBinary }); });
  upstream.on("close", (c) => { try { client.close(); } catch {} console.log("upstream close", c); });
  client.on("close", () => { try { upstream.close(); } catch {} });
  upstream.on("error", (e) => { console.error("upstream err:", e.message); try { client.close(); } catch {} });
  client.on("error", () => { try { upstream.close(); } catch {} });
});

server.listen(PORT, () => console.log(`WS relay on ws://localhost:${PORT} → ${BACKEND}`));

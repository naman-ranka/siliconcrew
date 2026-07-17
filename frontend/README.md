# SiliconCrew Architect - Frontend

A production-quality Next.js frontend for the RTL Design Agent, featuring a Claude-style interface with streaming chat, tool call visualization, and artifact viewers.

## Features

- **Three-panel layout**: Collapsible sidebar, resizable chat area, and artifacts panel
- **Real-time streaming**: WebSocket-based chat with live token streaming
- **Tool call visualization**: Collapsible cards showing tool execution and results
- **Artifact viewers**:
  - Spec: YAML specification with formatted and raw views
  - Code: Monaco editor for Verilog/SystemVerilog files
  - Waveform: VCD waveform visualization
  - Report: Markdown report viewer
- **Session management**: Create, switch, and delete design sessions
- **Keyboard shortcuts**: Cmd/Ctrl+B (sidebar), Cmd/Ctrl+] (artifacts), Cmd/Ctrl+K (focus input)

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Components**: shadcn/ui (Radix UI)
- **State**: Zustand
- **Editor**: Monaco Editor
- **Panels**: react-resizable-panels

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- FastAPI backend running on port 8000

### Installation

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at http://localhost:3000

### Running with Backend

1. Start the FastAPI backend:
```bash
# From project root
uvicorn api:app --reload --port 8000
```

2. Start the frontend:
```bash
cd frontend
npm run dev
```

## Project Structure

```
frontend/
├── app/
│   ├── layout.tsx      # Root layout with fonts and providers
│   ├── page.tsx        # Main page with panel layout
│   └── globals.css     # Global styles and CSS variables
├── components/
│   ├── ui/             # shadcn/ui components
│   ├── chat/           # Chat components
│   │   ├── ChatArea.tsx
│   │   ├── ChatInput.tsx
│   │   ├── MessageList.tsx
│   │   └── ToolCallCard.tsx
│   ├── sidebar/        # Sidebar components
│   │   └── Sidebar.tsx
│   └── artifacts/      # Artifact viewers
│       ├── ArtifactsPanel.tsx
│       ├── SpecViewer.tsx
│       ├── CodeViewer.tsx
│       ├── WaveformViewer.tsx
│       └── ReportViewer.tsx
├── lib/
│   ├── api.ts          # API client functions
│   ├── store.ts        # Zustand store
│   └── utils.ts        # Utility functions
├── hooks/
│   └── useKeyboardShortcuts.ts
└── types/
    └── index.ts        # TypeScript types
```

## API Integration

The frontend connects to the FastAPI backend via:

- **REST API**: Session management, workspace files
- **WebSocket**: Streaming chat responses

API calls are proxied through Next.js rewrites in `next.config.mjs`.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + B` | Toggle sidebar |
| `Cmd/Ctrl + ]` | Toggle artifacts panel |
| `Cmd/Ctrl + K` | Focus chat input |
| `Escape` | Close artifacts panel |
| `Enter` | Send message |
| `Shift + Enter` | New line in input |

## Environment Variables

Backend URLs are read at **runtime**, not build time, so a single image runs in
any environment (local, staging, prod) without rebuilding. The server layout
(`app/layout.tsx`) reads these and injects them into the page; the browser reads
them via `lib/runtime-config.ts` and talks to the backend directly.

| Var | Purpose | Default |
|-----|---------|---------|
| `API_URL` | Backend origin for REST (e.g. `https://siliconcrew-backend-….run.app`) | `http://localhost:8000` |
| `WS_URL`  | Backend origin for WebSocket | derived from `API_URL` (`http`→`ws`) |
| `GOOGLE_CLIENT_ID` | Google OAuth Web Client ID for sign-in (public value). Empty = no auth. | _(empty)_ |

> These are **not** `NEXT_PUBLIC_*` on purpose — `NEXT_PUBLIC_*` is inlined at
> build time, which is exactly what caused the prod `localhost:8000` /
> ECONNREFUSED bug. Keeping them plain (read per request, injected into the page
> by the server layout) means **one image runs in any environment** — including
> self-host (no auth) vs hosted (auth) without a rebuild.

For local dev, create `.env.local` (or just rely on the localhost defaults):

```env
API_URL=http://localhost:8000
WS_URL=ws://localhost:8000

# Google sign-in. Leave UNSET for self-host / local dev: no sign-in UI renders,
# no token is sent, full access (anonymous) — zero config. When set, a "Sign in
# with Google" button appears and the Google ID token is attached as
# `Authorization: Bearer <token>` on every API call (REST + WS). Must equal the
# backend's GOOGLE_OAUTH_CLIENT_ID (same OAuth client). Read at runtime, so no
# rebuild needed per environment.
GOOGLE_CLIENT_ID=
```

> Back-compat: `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is still honored as a fallback, but
> `GOOGLE_CLIENT_ID` (runtime) is preferred so the image stays env-agnostic.

The backend must allow the frontend origin via CORS — set `CORS_ALLOW_ORIGINS`
(comma-separated) or `CORS_ALLOW_ORIGIN_REGEX` on the backend. Local dev origins
(`http://localhost:3000`, `http://127.0.0.1:3000`) are always allowed.

### Hosted auth (Google sign-in)

The backend already verifies Google ID tokens (`GOOGLE_OAUTH_CLIENT_ID`); the
frontend only needs `GOOGLE_CLIENT_ID` set to the **same** client ID (injected at
runtime — no rebuild per environment).

| `GOOGLE_CLIENT_ID` | Behavior |
|--------------------|----------|
| **unset** | Self-host / dev default. No auth UI, no GIS script, no token sent. Anonymous trial = full local access. |
| **set**   | "Sign in" via WorkOS AuthKit (Google or email/password) or Google Identity Services. After sign-in the ID token rides `Authorization: Bearer` on REST and `?token=` on the chat WebSocket. Synth/save prompt sign-in when signed-out; lint/sim stay available. On a 401 the token is cleared → re-sign-in prompt. |

No `next-auth` / server callback — GIS hands us the ID token and the backend
re-verifies it. The decoded JWT is used for display only.

## Development

```bash
# Development server with hot reload
npm run dev

# Type checking
npx tsc --noEmit

# Linting
npm run lint

# Production build
npm run build
```

## Deployment

### Docker

The frontend can be containerized alongside the backend. See the root `docker-compose.yml` for the full setup.

### Vercel

For standalone frontend deployment:

```bash
npm run build
# Deploy the .next folder to Vercel
```

Set `API_URL` (and optionally `WS_URL`) on the deployment to point at your
deployed backend — these are read at runtime, so no rebuild is needed per env.

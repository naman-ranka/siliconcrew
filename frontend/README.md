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

Create a `.env.local` file for custom configuration:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

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

Ensure `NEXT_PUBLIC_API_URL` points to your deployed backend.

# SiliconCrew Architect - UI Design Requirements

**Document Version:** 1.0  
**Date:** February 2, 2026  
**Status:** Planning

---

## Overview

Redesign the SiliconCrew Architect frontend to provide a professional, modern UI similar to Claude.ai, replacing the current Gradio implementation.

### Goals
- Professional appearance suitable for demos and production
- Improved user experience with resizable, collapsible panels
- Better handling of streaming chat with tool calls
- Real-time artifact display (specs, code, waveforms)

---

## Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Header Bar (optional)                          │
│  Logo: SiliconCrew Architect    │    Model: gemini-2.5-flash    │ Tokens │
├──────────────┬──────────────────────────────────┬───────────────────────┤
│              │                                  │                       │
│   LEFT       │           CENTER                 │        RIGHT          │
│   SIDEBAR    │           CHAT AREA              │        ARTIFACTS      │
│              │                                  │        PANEL          │
│  (Sessions)  │     (Main Interaction)           │    (Specs, Code,      │
│              │                                  │     Waveforms)        │
│              │                                  │                       │
│  Collapsible │        Fixed/Expandable          │      Slide-in         │
│  ◀────────── │ ◀──────────────────────────────▶ │ ──────────────▶       │
│   ~250px     │         Remaining Space          │     ~400px            │
│              │                                  │    (Resizable)        │
└──────────────┴──────────────────────────────────┴───────────────────────┘
```

---

## Component Specifications

### 1. Left Sidebar (Session Management)

**Behavior:**
- Collapsible (icon-only when collapsed)
- Default width: 250px
- Can be toggled via hamburger icon or keyboard shortcut

**Contents:**
```
┌─────────────────────┐
│ ☰  SiliconCrew      │  ← Logo + collapse toggle
├─────────────────────┤
│ [+ New Session]     │  ← Primary action button
├─────────────────────┤
│ Sessions            │  ← Section header
│ ─────────────────── │
│ 📁 try_gardio_p5_1  │  ← Active session (highlighted)
│ 📁 counter_design   │
│ 📁 lfsr_project     │
│ 📁 ...              │
├─────────────────────┤
│ ⚙️ Settings         │  ← Bottom section
│ 📊 Usage Stats      │
└─────────────────────┘
```

**Features:**
- [ ] Session list with timestamps
- [ ] Right-click context menu (Rename, Delete, Duplicate)
- [ ] Search/filter sessions
- [ ] Session metadata preview on hover
- [ ] Drag to reorder (optional)

---

### 2. Center Chat Area

**Behavior:**
- Takes remaining horizontal space
- Scrollable message history
- Sticky input box at bottom

**Layout:**
```
┌─────────────────────────────────────────────┐
│                                             │
│  Message History (scrollable)               │
│  ─────────────────────────────────────────  │
│                                             │
│  👤 User: Design an 8-bit counter...        │
│                                             │
│  🤖 Assistant:                              │
│      I'll create a specification first.     │
│                                             │
│      ┌─────────────────────────────────┐    │
│      │ 🛠️ Tool: write_spec             │    │  ← Collapsible tool call
│      │    module: counter_8bit         │    │
│      │    ✅ Success                   │    │
│      └─────────────────────────────────┘    │
│                                             │
│      The specification has been created...  │
│                                             │
├─────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────┐ │
│ │ Message input...                    Send│ │  ← Sticky input
│ └─────────────────────────────────────────┘ │
│ Model: gemini-2.5-flash ▼  │  📎 Attach    │
└─────────────────────────────────────────────┘
```

**Features:**
- [ ] Streaming text display (token by token)
- [ ] Tool calls rendered as collapsible cards
- [ ] Tool results with status icons (✅❌⏳)
- [ ] Markdown rendering in messages
- [ ] Code syntax highlighting
- [ ] Copy button on code blocks
- [ ] Message timestamps (on hover)
- [ ] "Thinking..." indicator with elapsed time
- [ ] Stop generation button

---

### 3. Right Artifacts Panel

**Behavior:**
- Hidden by default
- Slides in when first artifact is created
- Resizable (drag left edge)
- Can be collapsed/hidden
- Default width: 400px
- Min width: 300px, Max width: 600px

**Layout:**
```
┌────────────────────────────────────┐
│ Artifacts              [─] [×]     │  ← Minimize/Close buttons
├────────────────────────────────────┤
│ [Spec] [Code] [Wave] [Layout] [📊] │  ← Tabs
├────────────────────────────────────┤
│                                    │
│  📋 dot_product_spec.yaml          │  ← File indicator
│  ──────────────────────────────    │
│                                    │
│  Module: dot_product               │
│  Description: Pipelined dot...     │
│                                    │
│  Ports:                            │
│  ┌──────┬───────┬───────┐          │
│  │ Name │ Dir   │ Width │          │
│  ├──────┼───────┼───────┤          │
│  │ clk  │ input │ 1     │          │
│  │ rst  │ input │ 1     │          │
│  │ ...  │ ...   │ ...   │          │
│  └──────┴───────┴───────┘          │
│                                    │
│  [📥 Download] [📋 Copy]           │
│                                    │
└────────────────────────────────────┘
```

**Tabs:**

| Tab | Content | Features |
|-----|---------|----------|
| **Spec** | YAML specification | Formatted display, raw toggle |
| **Code** | Verilog files | Syntax highlighting, file selector |
| **Waveform** | VCD visualization | Interactive zoom, signal selection |
| **Layout** | GDS viewer | Pan/zoom, layer toggle |
| **Report** | Design metrics | PPA summary, timing analysis |

**Features:**
- [ ] Auto-switch to relevant tab when artifact created
- [ ] Badge indicators for new/updated files
- [ ] File selector dropdown for multiple files
- [ ] Download individual files
- [ ] Download all as ZIP
- [ ] Full-screen mode for each tab

---

## Interaction Patterns

### Session Flow
```
User opens app
    │
    ├─► No previous sessions
    │       │
    │       └─► Show "Create your first session" prompt
    │
    └─► Has previous sessions
            │
            ├─► Auto-load last active session
            │
            └─► Or show session list to choose
```

### Artifact Panel Flow
```
User sends message
    │
    └─► Agent responds
            │
            ├─► Text only: No change to artifacts panel
            │
            └─► Tool creates artifact:
                    │
                    ├─► Panel hidden? Slide in
                    │
                    ├─► Switch to relevant tab
                    │
                    └─► Highlight new/updated file
```

---

## Visual Design

### Color Scheme (Dark Mode - Primary)

```css
/* Background colors */
--bg-primary: #1a1a2e;      /* Main background */
--bg-secondary: #16213e;    /* Sidebar, panels */
--bg-tertiary: #0f3460;     /* Cards, inputs */
--bg-hover: #1f4068;        /* Hover states */

/* Text colors */
--text-primary: #e8e8e8;    /* Primary text */
--text-secondary: #a0a0a0;  /* Secondary text */
--text-muted: #6b6b6b;      /* Muted text */

/* Accent colors */
--accent-primary: #4a90d9;  /* Primary actions */
--accent-success: #4ade80;  /* Success states */
--accent-warning: #fbbf24;  /* Warnings */
--accent-error: #f87171;    /* Errors */

/* Borders */
--border-color: #2a2a4a;    /* Default borders */
--border-active: #4a90d9;   /* Active/focus borders */
```

### Typography

```css
/* Font family */
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;

/* Font sizes */
--text-xs: 0.75rem;    /* 12px */
--text-sm: 0.875rem;   /* 14px */
--text-base: 1rem;     /* 16px */
--text-lg: 1.125rem;   /* 18px */
--text-xl: 1.25rem;    /* 20px */
```

### Spacing

```css
/* Consistent spacing scale */
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
```

---

## Responsive Behavior

### Breakpoints

| Breakpoint | Width | Layout Changes |
|------------|-------|----------------|
| Desktop XL | ≥1440px | All panels visible, comfortable spacing |
| Desktop | ≥1024px | All panels visible, compact spacing |
| Tablet | ≥768px | Sidebar collapsed by default, artifacts as overlay |
| Mobile | <768px | Single panel view, swipe navigation |

### Mobile Considerations
- Sidebar becomes full-screen overlay
- Artifacts panel becomes bottom sheet
- Chat remains primary view
- Swipe gestures for navigation

---

## Technical Requirements

### Performance
- [ ] Initial load < 2 seconds
- [ ] Message streaming latency < 100ms
- [ ] Smooth 60fps animations
- [ ] Lazy load artifacts (especially waveforms, GDS)

### Accessibility
- [ ] Keyboard navigation for all actions
- [ ] Screen reader support
- [ ] High contrast mode option
- [ ] Configurable font sizes

### Browser Support
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

---

## Implementation Choice: FastAPI + Next.js

### Why Next.js (Industry Standard)

| AI App | Frontend |
|--------|----------|
| ChatGPT | Next.js |
| Claude | Next.js |
| Perplexity | Next.js |
| v0.dev | Next.js |
| Most YC AI startups | Next.js |

**Decision:** Next.js is the de facto standard for AI chat applications in 2024-2026.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js)                       │
│                                                              │
│   - Chat UI with streaming                                   │
│   - Artifacts panel (Spec, Code, Waveform)                  │
│   - Session management                                       │
│                           │                                  │
│                           │ HTTP REST + WebSocket            │
│                           ▼                                  │
├─────────────────────────────────────────────────────────────┤
│                     BACKEND (FastAPI)                        │
│                                                              │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│   │  LangGraph  │    │   Tools     │    │  Session    │     │
│   │   Agent     │    │  (existing) │    │  Manager    │     │
│   └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                              │
│   Existing Python code - NO CHANGES to agent/tools          │
└─────────────────────────────────────────────────────────────┘
```

### Tech Stack

**Frontend (Next.js):**
```
- Next.js 14+ (App Router)
- TypeScript
- Tailwind CSS
- shadcn/ui components
- Vercel AI SDK (streaming)
- react-resizable-panels
- Monaco Editor (code display)
- Zustand (state management)
```

**Backend (FastAPI):**
```
- FastAPI (Python)
- WebSocket for streaming
- Existing LangGraph agent (no changes)
- Existing tools (no changes)
- SQLite (existing)
```

### Key Dependencies

```json
// package.json (frontend)
{
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "typescript": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "@radix-ui/react-*": "latest",
    "ai": "^3.0.0",
    "react-resizable-panels": "^2.0.0",
    "@monaco-editor/react": "^4.6.0",
    "zustand": "^4.5.0",
    "lucide-react": "^0.300.0"
  }
}
```

```txt
# requirements.txt additions (backend)
fastapi>=0.109.0
uvicorn>=0.27.0
websockets>=12.0
```

### API Endpoints (FastAPI)

```python
# Core endpoints needed

# Sessions
GET    /api/sessions                    # List all sessions
POST   /api/sessions                    # Create new session
DELETE /api/sessions/{id}               # Delete session
GET    /api/sessions/{id}               # Get session metadata

# Chat
WS     /api/chat/{session_id}           # WebSocket for streaming chat
GET    /api/chat/{session_id}/history   # Get chat history

# Workspace/Artifacts
GET    /api/workspace/{session_id}/files          # List all files
GET    /api/workspace/{session_id}/spec           # Get spec YAML
GET    /api/workspace/{session_id}/code           # Get Verilog files
GET    /api/workspace/{session_id}/code/{file}    # Get specific file
GET    /api/workspace/{session_id}/waveform       # Get VCD data
GET    /api/workspace/{session_id}/report         # Get design report
```

### Folder Structure

```
RTL_AGENT/
├── frontend/                    # Next.js app
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── ui/                  # shadcn components
│   │   ├── chat/
│   │   │   ├── ChatArea.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   └── ToolCallCard.tsx
│   │   ├── sidebar/
│   │   │   ├── Sidebar.tsx
│   │   │   └── SessionList.tsx
│   │   └── artifacts/
│   │       ├── ArtifactsPanel.tsx
│   │       ├── SpecViewer.tsx
│   │       ├── CodeViewer.tsx
│   │       └── WaveformViewer.tsx
│   ├── lib/
│   │   ├── api.ts               # API client
│   │   └── store.ts             # Zustand store
│   ├── package.json
│   └── tailwind.config.js
│
├── api.py                       # FastAPI server (NEW)
├── src/                         # Existing Python code (NO CHANGES)
│   ├── agents/
│   ├── tools/
│   └── utils/
├── gradio_app.py               # Keep for now (deprecated)
└── app.py                      # Streamlit (deprecated)
```

### Alternatives Considered (Not Chosen)

| Option | Why Not Chosen |
|--------|----------------|
| React + Vite | Not industry standard for AI apps |
| NiceGUI | Limited ecosystem, less professional |
| Reflex | Newer, smaller community |
| Gradio | Cannot achieve required UI (current limitation) |
| Streamlit | Same limitations as Gradio |

---

## Milestones

### Phase 1: Project Setup & Core Layout
- [ ] Initialize Next.js project with TypeScript + Tailwind
- [ ] Install and configure shadcn/ui
- [ ] Create FastAPI server (`api.py`)
- [ ] Three-panel layout (sidebar, chat, artifacts)
- [ ] Basic dark theme styling

### Phase 2: Session Management
- [ ] API endpoints for sessions (CRUD)
- [ ] Sidebar with session list
- [ ] Create new session flow
- [ ] Delete session with confirmation
- [ ] Session metadata display

### Phase 3: Chat Functionality
- [ ] WebSocket connection for streaming
- [ ] Message list component
- [ ] Streaming text display
- [ ] Tool call cards (collapsible)
- [ ] Tool result display with status icons
- [ ] Chat input with send button
- [ ] "Thinking..." indicator

### Phase 4: Artifacts Panel
- [ ] Tabbed interface (Spec, Code, Waveform, Layout, Report)
- [ ] Spec viewer with YAML parsing
- [ ] Code viewer with Monaco Editor
- [ ] File selector for multiple files
- [ ] Download buttons
- [ ] Auto-switch tabs on new artifacts

### Phase 5: Advanced Features
- [ ] Resizable panels (react-resizable-panels)
- [ ] Collapsible sidebar
- [ ] Waveform visualization
- [ ] GDS layout viewer (if feasible)
- [ ] Keyboard shortcuts

### Phase 6: Polish & Deploy
- [ ] Animations and transitions
- [ ] Loading states and skeletons
- [ ] Error handling and toasts
- [ ] Mobile responsive (basic)
- [ ] Performance optimization
- [ ] Docker setup for deployment

---

## Open Questions

1. **Authentication**: Do we need user accounts or is it single-user?
   - *Initial: Single-user, no auth*
   
2. **Persistence**: Keep SQLite or move to a proper database?
   - *Initial: Keep SQLite for simplicity*
   
3. **Deployment**: Docker, cloud hosting, or local only?
   - *Options: Docker Compose (frontend + backend) or Vercel (frontend) + Railway (backend)*
   
4. **Collaboration**: Multiple users viewing same session?
   - *Initial: No, single-user only*

5. **Monorepo vs Separate Repos?**
   - *Recommendation: Monorepo with `/frontend` folder*
   
6. **Port Configuration**
   - Frontend: `http://localhost:3000`
   - Backend: `http://localhost:8000`

---

## References

### UI Inspiration
- [Claude.ai](https://claude.ai) - Target UI inspiration
- [ChatGPT](https://chat.openai.com) - Alternative reference
- [Cursor IDE](https://cursor.sh) - Developer-focused chat UI

### Next.js & React
- [Next.js Docs](https://nextjs.org/docs) - Framework documentation
- [Vercel AI SDK](https://sdk.vercel.ai/docs) - Streaming chat helpers
- [shadcn/ui](https://ui.shadcn.com) - Component library
- [react-resizable-panels](https://github.com/bvaughn/react-resizable-panels) - Panel resizing
- [Zustand](https://zustand-demo.pmnd.rs/) - State management

### FastAPI
- [FastAPI Docs](https://fastapi.tiangolo.com/) - Backend framework
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) - Streaming

### Code Examples
- [Vercel AI Chatbot](https://github.com/vercel/ai-chatbot) - Reference implementation
- [ChatGPT Clone](https://github.com/mckaywrigley/chatbot-ui) - Open source clone

---

## Appendix A: Why Not Gradio/Streamlit

| Feature | Gradio | Streamlit | Next.js |
|---------|--------|-----------|---------|
| Collapsible sidebar | ❌ | ⚠️ | ✅ |
| Resizable panels | ❌ | ❌ | ✅ |
| Slide-in panels | ❌ | ❌ | ✅ |
| Smooth animations | ❌ | ❌ | ✅ |
| True streaming | ⚠️ Polling | ⚠️ Polling | ✅ WebSocket |
| Professional look | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| Industry standard | ❌ | ❌ | ✅ |

**Decision:** Next.js is necessary for the required UI quality and industry alignment.

---

## Appendix B: Getting Started Commands

```bash
# 1. Create Next.js frontend
cd RTL_AGENT
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"

# 2. Install shadcn/ui
cd frontend
npx shadcn-ui@latest init

# 3. Install additional dependencies
npm install ai react-resizable-panels @monaco-editor/react zustand lucide-react

# 4. Install FastAPI (backend)
cd ..
pip install fastapi uvicorn websockets

# 5. Run both servers
# Terminal 1: Backend
uvicorn api:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

---

## Appendix C: Development Timeline Estimate

| Phase | Estimated Time |
|-------|----------------|
| Phase 1: Setup & Layout | 1 day |
| Phase 2: Session Management | 1 day |
| Phase 3: Chat Functionality | 2 days |
| Phase 4: Artifacts Panel | 2 days |
| Phase 5: Advanced Features | 2 days |
| Phase 6: Polish & Deploy | 1 day |
| **Total** | **~9 days** |

*Note: Timeline assumes familiarity with React/Next.js. Add buffer for learning curve if needed.*

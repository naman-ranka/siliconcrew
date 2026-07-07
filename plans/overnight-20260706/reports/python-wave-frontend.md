# Python analysis wave — frontend (PA7–PA10)

Branch `claude/overnight-showcase`. Frontend portion of
`plans/python-analysis-and-artifacts.md` (Amendments authoritative). Four
per-item commits, pushed. Fence: `frontend/**` + this report only; no backend
files touched.

## Cross-lane contract decision (Item 4 / PA11 — no backend change requested)

The backend deferred Item 4 (`/file`,`/dir` kind/MIME enrichment) so my
consumption would define the contract. **My viewers do NOT need it.** Kind is
determined entirely client-side:
- The tool card opens artifacts by KEY (`image:<path>` / `data:<path>` /
  `text:<path>`), and the key's kind comes from `run_python_analysis`'s own
  structured result (`artifacts:[{path,kind,bytes}]`) — parsed in PA9.
- Opening the same families from the file tree / QuickOpen uses extension-based
  routing in `artifactKeyForFile` (PA8), exactly as the plan's Item 5
  prescribes.
- The viewers fetch bytes/content through EXISTING endpoints: images via a new
  authed blob helper on `/file?raw=1`; data/text via the smart-file reader
  (`getFileSmart`), which already returns `content|null` + `binary`/`tooLarge`.

So the backend lane does NOT need to apply its documented Item-4 diff for these
viewers to work. It remains a nice-to-have (a server-authoritative kind for
files the extension map can't classify), but nothing here consumes it. **No new
`/file` fields requested.**

## Commits

1. `feat(ui): image/data/text artifact viewers + blob-URL raw fetch (PA7)`
2. `feat(ui): wire image/data/text ArtifactKind + file routing (PA8)`
3. `feat(ui): map run_python_analysis artifacts to an open key (PA9)`
4. `feat(ui): file-combo convention for script_file params (PA10)`

## PA7 — viewers + blob fix

- `lib/api.ts`: `workspaceApi.fetchRawObjectUrl(sid, path)` — fetches
  `/file?raw=1` WITH the Bearer header, returns `URL.createObjectURL(blob)`.
  The blob-URL fix the amendments call out: a bare `<img src=…?raw=1>` 401s
  (header-only auth) and `downloadRawFile` force-downloads. Caller owns the URL.
- `ImageArtifact` — png/jpg/webp/gif/svg via that blob URL; revokes on
  unmount/path change; SVG through `<img>` (never inline HTML → can't script);
  checkerboard bg; download button; honest error state.
- `DataArtifact` — CSV/TSV → capped table (500 rows × 40 cols) with honest
  "showing N of M"; JSON pretty-printed; YAML/other → monospace (no YAML parser
  shipped, and YAML is already readable). Parses the whole ≤1MB smart-file so
  the counts are accurate. `parseDelimited` is exported + unit-tested (quoted
  fields, row cap).
- `TextArtifact` — monospace txt/log/rpt via the smart-file cache; honest
  binary/too-large states.

## PA8 — ArtifactKind wiring + routing (a FULLER consumer sweep than "4 sites")

The plan named 4 edit sites; tsc caught **two more** exhaustive
`Record<ArtifactKind,…>` maps the amendment missed:
- Plan's 4: `types` union, `REF_KINDS` (parse), `ArtifactCenter` `KIND_ICON`,
  `ArtifactBody` switch.
- Extra 2: `QuickOpen` (KIND_ICON + KIND_NAME) and `ToolCallCard` (KIND_ICON +
  KIND_OPEN_LABEL). All widened, or tsc breaks.
- `openArtifact.artifactKeyForFile`: raster images→`image:`, csv/tsv/json/yaml
  →`data:`, txt/log/rpt→`text:` — inserted AFTER the run-scoped/schematic/spec
  routing so `.svg` stays schematic and `*_spec.yaml` stays spec. `artifactLabel`
  labels the new file-backed kinds by basename.

## PA9 — tool-result → open key

`run_python_analysis` case in `toolArtifacts.ts`: parse the result JSON, open
ONE primary artifact — first image, else data, else text (all have viewers) —
falling back to the input script (`code:`) when only vector/file artifacts exist
or the result isn't JSON. Multi-artifact cards stay deferred (per PA9).

## PA10 — file combo for `script_file`

`schemaForm.ts`: new `FILE_KEYS` set (filename/file_path/spec_file/script_file)
→ `script_file` renders a workspace-file combo in the Command Surface
(suggestions + free entry).

## Tests (vitest, all green)

- `pythonViewers.test.tsx` (9): parseDelimited (quotes, cap); ImageArtifact
  renders from a mocked blob URL + honest fetch-error; DataArtifact CSV table,
  row-cap "showing 500 of 900", JSON pretty; TextArtifact content + binary.
- `artifactKeys.test.ts`: parse round-trip for image/data/text.
- `openArtifact.routing.test.ts` (new): extension routing + basename labels +
  run-scoped precedence.
- `toolArtifacts.test.ts`: PA9 mapping (image>data>text>script; unparseable →
  script; no script → null).
- `schemaForm.test.ts`: `script_file` → root files.

## Gates

- `tsc --noEmit` clean; `vitest run` 393 passed, **1** failure = the known
  pre-existing `chat.threads.store.test.ts` only (zero new); `next build` green.
- No Playwright (endgame owns the browser).

## Browser-only (for the endgame Playwright pass)

- Run a tiny script via the Command Surface (script_file combo) → the tool card
  shows "Open image →" → the ImageArtifact renders the PNG (authed blob, not a
  401/download) with the checkerboard bg.
- Open a `.csv` from the tree → DataArtifact table; a `.log` → TextArtifact; a
  `.json` → pretty tree. Verify the blob URL renders (jsdom can't exercise real
  object URLs — the unit test mocks the helper).
- Confirm SVG still opens in the schematic viewer (not image) and `*_spec.yaml`
  still opens as the spec.

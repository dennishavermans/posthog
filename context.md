# Code Context

## Files Retrieved

1. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/types.d.ts` (lines 45-152, 929-958) — exact extension UI API, including `custom`, overlay options/handle, and `pi.sendUserMessage`.
2. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-tui/dist/tui.d.ts` (lines 5-113, 127-145) — component, overlay, terminal-size, focus, and rendering contracts.
3. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-tui/dist/tui.js` (lines 679-846) — actual overlay sizing/compositing behavior that permits full-screen coverage.
4. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/dist/modes/interactive/interactive-mode.js` (lines 2140-2212) — `custom()` lifecycle implementation and its topmost-overlay close behavior.
5. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/docs/extensions.md` (lines 1389-1459, 2493-2764, 2888-2906) — supported persistence, turn injection, mode restrictions, and documented experimental-overlay status.
6. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/docs/tui.md` (lines 9-41, 109-173) — required render width, focus/cursor, overlay lifecycle, and full overlay options.
7. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/examples/extensions/overlay-test.ts` (lines 12-148) — minimal focused overlay component with `done`, `matchesKey`, `Focusable`, and `CURSOR_MARKER`.
8. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/examples/extensions/doom-overlay/index.ts` (lines 14-72) and `doom-component.ts` (lines 45-99) — long-running, real-time overlay and cleanup pattern.
9. `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/examples/extensions/send-user-message.ts` (lines 14-75) — correct idle/streaming behavior for extension-driven turns.

## Key Code

### Safest supported shape

- Load as a global extension in `~/.pi/agent/extensions/<name>.ts` (or project `.pi/extensions/`) so it is auto-discovered and `/reload`-able: `docs/extensions.md:29-61`.
- Guard all overlay work with `ctx.mode === "tui"`. `custom()` is terminal-only; in RPC it returns `undefined`, while print/JSON have no UI: `docs/extensions.md:2888-2906` and `types.d.ts:186-190`.
- Keep one `ctx.ui.custom()` promise alive for the overlay. Its component gets keyboard focus; use `done()` only to intentionally close it. Do **not** await that promise from `session_start`, because it is designed to remain unresolved while open. Start it fire-and-forget with a caught rejection, and prevent duplicate opens with an in-memory `opening/open` flag.
- In the component submit handler, call `pi.sendUserMessage(text)` when idle. It always creates an actual user message and triggers a turn. When streaming, choose an explicit policy: `{ deliverAs: "followUp" }` is least disruptive; `{ deliverAs: "steer" }` intentionally interrupts after current tool execution. Calling without `deliverAs` while streaming throws (`docs/extensions.md:1412-1440`; example lines 26-70).
- Update the panel’s model/working state from `agent_start`, `message_update`, `tool_execution_*`, `agent_end`, or preferably `agent_settled`; call the retained `tui.requestRender()` after state mutation. Those events exist in `types.d.ts:448-491`.

### Full-screen visual concealment

Use an overlay rather than replacing the core editor:

```ts
await ctx.ui.custom((tui, theme, _keys, done) => new AgentOverlay(tui, theme, done), {
  overlay: true,
  overlayOptions: { width: '100%', maxHeight: '100%', row: 0, col: 0 },
})
```

`AgentOverlay.render(width)` must return **exactly** `tui.terminal.rows` lines, and every line must occupy all `width` columns (pad with spaces; add an explicit background style if desired). `tui.terminal.columns/rows` are available (`terminal.d.ts:27-28`). This is essential: overlays composite only the characters they render over the transcript; short lines/short height expose the underlying transcript. The compositor pads its working area to terminal height and uses screen-relative `row: 0`, then overlays line-by-line (`tui.js:802-846`). `width: "100%"`, `row: 0`, `col: 0`, and `maxHeight: "100%"` are supported `OverlayOptions` (`tui.d.ts:48-94`).

The component contract requires visible width no greater than `width`; use `truncateToWidth`/`visibleWidth` for dynamic text (`docs/tui.md:9-18`). If it accepts text, implement `Focusable` and emit `CURSOR_MARKER` while focused, as shown in `overlay-test.ts:36-148`; otherwise IME cursor placement is wrong.

### Persistence

- Overlay UI itself is not durable. On `/reload`, `/new`, `/resume`, or `/fork`, the extension runtime is re-created; clean resources in `session_shutdown` and reopen from `session_start` (`docs/extensions.md:388-444`). `dispose()` must clear timers/listeners, as the Doom component does (`doom-component.ts:57-99`).
- Persist only small durable state (enabled flag, draft, selected mode) with `pi.appendEntry("my-overlay-state", data)`. Restore by scanning `ctx.sessionManager.getEntries()` in `session_start`; custom entries stay out of LLM context (`docs/extensions.md:1444-1459`). Do not append on every paint/update: it creates session entries.
- The transcript is **not removed**, only visually covered. Pi has no exposed API to hide/replace the chat transcript. It remains in session storage/LLM context and will be revealed if the overlay closes or fails.

## Architecture

`session_start` establishes session-local UI and restores extension state. The persistent focused `ctx.ui.custom(..., { overlay: true })` component owns keyboard input. Its submit handler dispatches `pi.sendUserMessage`; Pi runs normal input events and the agent loop. Lifecycle events mutate panel state and request redraws while the overlay covers the regular main-screen transcript. `session_shutdown` disposes resources; the next `session_start` builds a fresh panel.

## Review Findings

- **high — experimental/API risk:** Overlay mode is explicitly marked “Experimental” (`docs/extensions.md:2733-2764`). Pin/test against the local Pi version; do not rely on undocumented internals.
- **high — visual-only privacy:** No transcript-hiding API exists. A full-size overlay only composites over the viewport (`tui.js:802-846`); transcript is still retained and is visible on close/failure.
- **medium — accidental transcript leak:** Any render line narrower than overlay width, or fewer than `terminal.rows`, reveals underlying content. Pad every row and recompute height every render.
- **medium — close-order pitfall:** Pi closes `custom({overlay:true})` via `this.ui.hideOverlay()`, which hides the **topmost** overlay, not the specific handle (`interactive-mode.js:2154-2157`). Keep this as the only capturing overlay; do not stack modals over it unless close order is controlled.
- **medium — turn-dispatch race:** `sendUserMessage` throws if streaming and no `deliverAs` is supplied. Check `ctx.isIdle()` immediately before dispatch and catch synchronous errors; select `followUp`/`steer` deliberately.
- **low — non-TUI behavior:** Calling `custom()` outside `tui` is unsupported/no-op-like; gate on `ctx.mode === "tui"`.

## Start Here

Open `/Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent/examples/extensions/overlay-test.ts` first. It is the smallest working overlay using the exact local types; combine its component pattern with `send-user-message.ts` turn dispatch and the full-screen sizing above.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Concrete local Pi API findings, examples, implementation path, and severity-tagged risks are cited above."
    }
  ],
  "changedFiles": [
    "context.md"
  ],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "pi --help; local Pi package/type/example inspection",
      "result": "passed",
      "summary": "Located installed Pi at /Users/fcgomes/.local/lib/node_modules/@earendil-works/pi-coding-agent and inspected its declarations, implementation, docs, and examples."
    }
  ],
  "validationOutput": [
    "Findings are based on installed local declarations and implementation, not inferred APIs."
  ],
  "residualRisks": [
    "Overlay is experimental and only visually conceals, rather than removes, transcript data.",
    "Overlay sizing/rendering mistakes can expose transcript content."
  ],
  "noStagedFiles": true,
  "diffSummary": "Added read-only Pi extension implementation notes to context.md.",
  "reviewFindings": [
    "high: docs/extensions.md:2733-2764 - overlay mode is experimental.",
    "high: tui.js:802-846 - overlays composite over, rather than remove, the transcript.",
    "medium: interactive-mode.js:2154-2157 - closing an overlay hides the topmost overlay."
  ],
  "manualNotes": "No source code was modified; context.md is the required scouting artifact."
}
```

<script lang="ts">
  // Row 21 integration harness - the browser proof that the FIFTH Game works
  // inside the real runtime: a real Runtime, StorageService, SessionShell and
  // SessionRunner, resolving `crossword` through the PRODUCTION registry (so the
  // lazy code-split loader is exercised, not bypassed). Reached only via
  // `?harness=crossword`.
  //
  // Its session id is date-stable, so a reload resumes the same saved session -
  // which is what the e2e uses to prove the state round-trip.
  import SessionShell from "./SessionShell.svelte";
  import { createRuntime } from "../telemetry/runtime";
  import { StorageService } from "../services/StorageService";
  import { SessionRunner, type SessionHost } from "../session/SessionRunner";
  import { GAME_REGISTRY } from "../games/registry";
  import type { Session, SessionResult } from "../session/types";

  const runtime = createRuntime({ dev: import.meta.env.DEV });
  const storage = new StorageService({ store: localStorage });

  // A REAL baked board, lifted from the committed served set through the real
  // solver rather than hand-typed, and escaped like datasets/fixtures/* so the
  // file's own normalization form cannot change what it means.
  //
  // It is the easy band's mask: four answers of five ezhuthu crossing at four
  // squares, every answer starting on an unchecked square - the shape the row's
  // measurement settled on, because a Tamil word beginning with an independent
  // vowel cannot be crossed on its first letter.
  const BOARD = {
    rows: 5,
    cols: 5,
    entries: [
      {
        number: 3,
        direction: "across" as const,
        start: { row: 1, col: 0 },
        word: "\u0ba4\u0bc0\u0b9a\u0bcd\u0b9a\u0bc1\u0b9f\u0bb0\u0bcd",
        clue: "\u0b9a\u0bc1\u0bb5\u0bbe\u0bb2\u0bc8",
      },
      {
        number: 4,
        direction: "across" as const,
        start: { row: 3, col: 0 },
        word: "\u0bae\u0bb2\u0b95\u0bcd\u0b95\u0bae\u0bcd",
        clue: "\u0bae\u0bb2\u0b95\u0bcd\u0b95\u0b9f\u0bbf",
      },
      {
        number: 1,
        direction: "down" as const,
        start: { row: 0, col: 1 },
        word: "\u0b95\u0bc8\u0b9a\u0bcd\u0b9a\u0bc6\u0bb2\u0bb5\u0bc1",
        clue: "\u0b9a\u0bca\u0ba8\u0bcd\u0ba4\u0b9a\u0bcd \u0b9a\u0bc6\u0bb2\u0bb5\u0bc1",
      },
      {
        number: 2,
        direction: "down" as const,
        start: { row: 0, col: 3 },
        word: "\u0ba4\u0bca\u0b9f\u0b95\u0bcd\u0b95\u0bae\u0bcd",
        clue: "\u0b86\u0bb0\u0bae\u0bcd\u0baa\u0bae\u0bcd",
      },
    ],
  };

  const today = new Date().toISOString().slice(0, 10);
  const session: Session = {
    modeId: "harness-crossword",
    packId: "ta-core",
    gameId: "crossword",
    sessionId: `harness-crossword-${today}`,
    date: today,
    items: [{ gameId: "crossword", payload: BOARD }],
  };

  let progress = $state<{ completed: number; total: number } | null>(null);
  let stageEl = $state<HTMLElement | undefined>();
  let started = false;

  function renderSummary(result: SessionResult): void {
    const stage = stageEl;
    if (stage === undefined) return;
    const panel = document.createElement("div");
    panel.setAttribute("data-testid", "session-summary");
    panel.className = "flex flex-col items-center gap-sm anim-pop";
    const heading = document.createElement("h2");
    heading.className = "font-display text-lg text-success";
    heading.textContent = "Session complete";
    const detail = document.createElement("p");
    detail.className = "text-text-secondary";
    detail.textContent = `${result.itemsCompleted}/${result.itemsTotal} - ${result.totalScore} points`;
    panel.append(heading, detail);
    stage.replaceChildren(panel);
  }

  $effect(() => {
    if (stageEl === undefined || started) return;
    started = true;
    const host: SessionHost = {
      get stage() {
        return stageEl as HTMLElement;
      },
      setProgress(completed, total) {
        progress = { completed, total };
      },
      showSummary(result) {
        renderSummary(result);
      },
      clearStage() {
        stageEl?.replaceChildren();
      },
    };
    const runner = new SessionRunner({
      session,
      registry: GAME_REGISTRY,
      storage,
      logger: runtime.logger,
      bus: runtime.bus,
      host,
    });
    void runner.start();
  });
</script>

<SessionShell
  logger={runtime.logger}
  title="Crossword harness"
  {progress}
  bind:stage={stageEl}
/>

<script lang="ts">
  // Row 20 integration harness - the browser proof that the FOURTH Game works
  // inside the real runtime: a real Runtime, StorageService, SessionShell and
  // SessionRunner, resolving `word-search` through the PRODUCTION registry (so
  // the lazy code-split loader is exercised, not bypassed). Reached only via
  // `?harness=word-search`.
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
  // generator rather than hand-typed, and escaped like datasets/fixtures/* so
  // the file's own normalization form cannot change what it means.
  //
  // It was chosen for what it exercises rather than for what it says: four
  // words running in four different directions - one of them backwards up a
  // diagonal - and one unintended word the filler made, so the harness can
  // drive the "that is a word, but not on today's list" answer as well as a win.
  const BOARD = {
    grid: [
      ["\u0bb2\u0bcd", "\u0bae\u0bcd", "\u0bb2\u0bcd", "\u0bae\u0bcd", "\u0bb2\u0bc1", "\u0b95", "\u0bb2\u0bc1", "\u0b83"],
      ["\u0bae", "\u0ba4\u0bbf", "\u0bb0\u0bc1", "\u0bae", "\u0ba3", "\u0ba4\u0bbf", "\u0b85", "\u0ba3"],
      ["\u0b85", "\u0bae", "\u0bae\u0bbe", "\u0ba3", "\u0bae", "\u0ba4\u0bbf", "\u0bb0\u0bc1", "\u0bb0\u0bc1"],
      ["\u0ba4\u0bbf", "\u0b83", "\u0bb2\u0bc1", "\u0bb2\u0bcd", "\u0bb2\u0bcd", "\u0bb2\u0bc8", "\u0bb0\u0bc1", "\u0ba9\u0bcd"],
      ["\u0bb2\u0bcd", "\u0bb2\u0bc1", "\u0b95", "\u0bb2\u0bc1", "\u0baf", "\u0bae\u0bcd", "\u0bae\u0bbe", "\u0ba4\u0bbf"],
      ["\u0bb2\u0bc8", "\u0bb2\u0bc8", "\u0bae\u0bc1", "\u0bae\u0bcd", "\u0ba4\u0bbf", "\u0baf", "\u0ba9\u0bcd", "\u0baf"],
      ["\u0bae\u0bc1", "\u0bb2\u0bcd", "\u0b85", "\u0bb2\u0bcd", "\u0bb2\u0bc8", "\u0bae\u0bc1", "\u0bae", "\u0baf"],
      ["\u0bb2\u0bc1", "\u0b85", "\u0b95", "\u0bae", "\u0ba4\u0bbf", "\u0bae\u0bbe", "\u0ba9\u0bcd", "\u0b83"],
    ],
    targets: [
      {
        word: "\u0ba4\u0bbf\u0bb2\u0bcd\u0bb2\u0bc1\u0bae\u0bc1\u0bb2\u0bcd\u0bb2\u0bc1",
        start: { row: 2, col: 5 },
        direction: "down-left" as const,
        meaning: "\u0baa\u0bbf\u0ba4\u0bcd\u0ba4\u0bb2\u0bbe\u0b9f\u0bcd\u0b9f\u0bae\u0bcd",
      },
      {
        word: "\u0bae\u0bb2\u0bc8\u0baf\u0bae\u0bbe\u0ba9\u0bcd",
        start: { row: 7, col: 3 },
        direction: "up-right" as const,
        meaning: "\u0b9a\u0bc7\u0bb0\u0ba9\u0bcd",
      },
      {
        word: "\u0b85\u0b83\u0b95\u0bae\u0bcd",
        start: { row: 2, col: 0 },
        direction: "down-right" as const,
        meaning: "\u0ba4\u0bbe\u0ba9\u0bbf\u0baf\u0bae\u0bcd",
      },
      {
        word: "\u0ba4\u0bbf\u0bb0\u0bc1\u0bae\u0ba3",
        start: { row: 1, col: 1 },
        direction: "right" as const,
        meaning: "\u0bae\u0ba3\u0bae\u0bbe\u0ba9",
      },
    ],
    alsoValid: ["\u0b85\u0b95\u0bae\u0ba4\u0bbf"],
  };

  const today = new Date().toISOString().slice(0, 10);
  const session: Session = {
    modeId: "harness-word-search",
    packId: "ta-core",
    gameId: "word-search",
    sessionId: `harness-word-search-${today}`,
    date: today,
    items: [{ gameId: "word-search", payload: BOARD }],
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
  title="Word search harness"
  {progress}
  bind:stage={stageEl}
/>

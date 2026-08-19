<script lang="ts">
  // Row 18 integration harness - the browser proof that the SECOND Game works
  // inside the real runtime: a real Runtime, StorageService, SessionShell and
  // SessionRunner, resolving `missing-letters` through the PRODUCTION registry
  // (so the lazy code-split loader is exercised, not bypassed). Reached only via
  // `?harness=missing-letters`.
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

  // Both fixtures are REAL baked payloads, lifted from the committed served set
  // through the real generator rather than hand-typed, and escaped like
  // datasets/fixtures/* so the file's own normalization form cannot change what
  // they mean.
  //
  // "\u0B9A\u0BBF\u0BB1\u0BC1\u0B95\u0BA4\u0BC8" (sirukathai, a short story):
  // four ezhuthu with the second hidden, and a two-rung ladder.
  const SOLO = {
    word: "\u0B9A\u0BBF\u0BB1\u0BC1\u0B95\u0BA4\u0BC8",
    blanks: [1],
    choices: [
      "\u0B9A\u0BC8",
      "\u0B95\u0BC0",
      "\u0BB1\u0BC1",
      "\u0BAE\u0BC6",
      "\u0BAE\u0BC8",
      "\u0BB3\u0BC1",
      "\u0BB2\u0BBF",
      "\u0BB5\u0BC0",
    ],
    attempts: 3,
    hints: [
      { kind: "category", text: "\u0BB5\u0B95\u0BC8: \u0B95\u0BB2\u0BC8", cost: 1 },
      { kind: "meaning", text: "\u0BAA\u0BCA\u0BB0\u0BC1\u0BB3\u0BCD: \u0B95\u0BA4\u0BC8", cost: 3 },
    ],
    meaning: "\u0B95\u0BA4\u0BC8",
  };

  // The THIRD STATE's fixture, reached with `&fixture=also-valid`. The mask
  // "\u0B87 _ \u0B9F\u0BCD\u0B9F\u0BC8" really is answered by two served words -
  // "\u0B87\u0BB0\u0B9F\u0BCD\u0B9F\u0BC8" (a pair) and
  // "\u0B87\u0BB0\u0BBE\u0B9F\u0BCD\u0B9F\u0BC8" (a spinning wheel) - and both
  // fillers are in the bank, so the alternative can be driven on purpose.
  const PAIRED = {
    word: "\u0B87\u0BB0\u0B9F\u0BCD\u0B9F\u0BC8",
    blanks: [1],
    choices: [
      "\u0BB2\u0BCD",
      "\u0BB0",
      "\u0BB1\u0BCB",
      "\u0BA9\u0BCB",
      "\u0BAF\u0BCD",
      "\u0BB0\u0BBE",
      "\u0BA3\u0BBE",
      "\u0BB5\u0BCB",
    ],
    attempts: 3,
    alsoValid: ["\u0B87\u0BB0\u0BBE\u0B9F\u0BCD\u0B9F\u0BC8"],
  };

  const variant =
    new URLSearchParams(window.location.search).get("fixture") === "also-valid"
      ? "also-valid"
      : "solo";
  const payload = variant === "also-valid" ? PAIRED : SOLO;

  const today = new Date().toISOString().slice(0, 10);
  const session: Session = {
    modeId: "harness-missing-letters",
    packId: "ta-core",
    gameId: "missing-letters",
    // Scoped by variant as well as by date, so one fixture's saved run can
    // never restore into the other's puzzle.
    sessionId: `harness-missing-letters-${variant}-${today}`,
    date: today,
    items: [{ gameId: "missing-letters", payload }],
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
  title="Missing letters harness"
  {progress}
  bind:stage={stageEl}
/>

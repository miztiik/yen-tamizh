<script lang="ts">
  // Row 16 integration harness - the browser proof that the SIXTH Game works
  // inside the real runtime: a real Runtime, StorageService, SessionShell and
  // SessionRunner, resolving `word-ladder` through the PRODUCTION registry (so
  // the lazy code-split loader is exercised, not bypassed). Reached only via
  // `?harness=word-ladder`.
  //
  // Its session id is date-stable, so a reload resumes the same saved session -
  // which is what the e2e uses to prove the state round-trip.
  import SessionShell from "./SessionShell.svelte";
  import { createRuntime } from "../telemetry/runtime";
  import { StorageService } from "../services/StorageService";
  import { SessionRunner, type SessionHost } from "../session/SessionRunner";
  import { GAME_REGISTRY } from "../games/registry";
  import type { Session, SessionResult } from "../session/types";
  import { copyText } from "../lib/config";

  const runtime = createRuntime({ dev: import.meta.env.DEV });
  const storage = new StorageService({ store: localStorage });

  // A REAL baked climb - the committed contract fixture
  // (datasets/fixtures/contracts/word-ladder-puzzle_valid.json), lifted from
  // the served set through the real generator rather than hand-typed, and
  // escaped like datasets/fixtures/* so the file's own normalization form
  // cannot change what it means.
  //
  // "\u0B92\u0BB0\u0BC1" (oru, one) climbs to "\u0B92\u0BB0\u0BC1\u0BAE\u0BC8"
  // by adding "\u0BAE\u0BC8" and then to
  // "\u0B92\u0BB0\u0BC1\u0BAE\u0BC8\u0BAF" by adding "\u0BAF". The middle rung
  // is reachable three OTHER ways from the same bank, so the third state (a
  // pick that spells a real served word) can be driven on purpose.
  const CLIMB = {
    rungs: [
      {
        word: "\u0b92\u0bb0\u0bc1",
        meaning: "\u0b85\u0bb4\u0bbf\u0b9e\u0bcd\u0b9a\u0bbf\u0bb2\u0bcd",
      },
      {
        word: "\u0b92\u0bb0\u0bc1\u0bae\u0bc8",
        meaning: "\u0b87\u0bb1\u0bc8\u0baf\u0bc1\u0ba3\u0bb0\u0bcd\u0bb5\u0bc1",
        alsoValid: [
          "\u0b92\u0bb0\u0bc1\u0b95\u0bc8",
          "\u0b92\u0bb0\u0bc1\u0bae\u0bbe",
          "\u0b92\u0bb0\u0bc1\u0bb5\u0bc1",
        ],
      },
      {
        word: "\u0b92\u0bb0\u0bc1\u0bae\u0bc8\u0baf",
        meaning:
          "\u0b92\u0bb0\u0bc7 \u0bae\u0bc8\u0baf\u0bae\u0bcd \u0b95\u0bca\u0ba3\u0bcd\u0b9f \u0baa\u0bb2 \u0bb5\u0b9f\u0bbf\u0bb5\u0b99\u0bcd\u0b95\u0bb3\u0bcd",
      },
    ],
    choices: [
      "\u0b9a\u0bc8",
      "\u0bae\u0bc8",
      "\u0bb5\u0bc1",
      "\u0baf",
      "\u0b9a\u0bbf",
      "\u0bae\u0bbe",
      "\u0baa\u0bca",
      "\u0b95\u0bc8",
    ],
    timeLimitSec: 0,
  };

  const today = new Date().toISOString().slice(0, 10);
  const session: Session = {
    modeId: "harness-word-ladder",
    packId: "ta-core",
    gameId: "word-ladder",
    sessionId: `harness-word-ladder-${today}`,
    date: today,
    items: [{ gameId: "word-ladder", payload: CLIMB }],
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
      // The same slice the Daily hands down: the copy a Game may not import,
      // and the streak it may not read off storage itself.
      config: {
        labels: {
          alsoValid: copyText("anagram-also-valid"),
          statTime: copyText("stat-time"),
          statInstinct: copyText("stat-instinct"),
          statRetries: copyText("stat-retries"),
          statStreak: copyText("summary-streak"),
          share: copyText("action-share"),
          shared: copyText("action-shared"),
          continueOn: copyText("action-continue"),
        },
        streak: storage.loadSave()?.streak ?? 0,
      },
    });
    void runner.start();
  });
</script>

<SessionShell
  logger={runtime.logger}
  title="Word ladder harness"
  {progress}
  bind:stage={stageEl}
/>

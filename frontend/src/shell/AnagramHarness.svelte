<script lang="ts">
  // Row 12 integration harness - the browser proof that the FIRST PLAYABLE Game
  // works inside the real runtime: a real Runtime, StorageService, SessionShell
  // and SessionRunner, resolving `anagram` through the PRODUCTION registry (so
  // the lazy code-split loader is exercised, not bypassed). Reached only via
  // `?harness=anagram`; Row 13's Home + DailyMode replaces it with real chrome.
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

  // "\u0BA4\u0BAE\u0BBF\u0BB4\u0BCD" (tamizh): 3 ezhuthu, the last a mei cluster.
  // Escaped like datasets/fixtures/*, so the fixture is NFC/NFD-unambiguous.
  const SOLO = {
    word: "\u0BA4\u0BAE\u0BBF\u0BB4\u0BCD",
    tiles: ["\u0BA4", "\u0BAE\u0BBF", "\u0BB4\u0BCD"],
    reveal: 1,
    timeLimitSec: 0,
    attempts: 3,
    hints: [{ kind: "reveal-first", text: "\u0BAE\u0BC1\u0BA4\u0BB2\u0BCD: \u0BA4", cost: 2 }],
  };

  // The THIRD STATE's fixture, reached with `&fixture=also-valid`:
  // "\u0B85\u0BA4\u0BBF\u0B95" (adhiga) and "\u0B85\u0B95\u0BA4\u0BBF" (agadhi)
  // are a real served anagram PAIR, so an arrangement that is a word but not
  // today's can be driven on purpose. The committed bank cannot be relied on
  // for it: only 1.6% of served words have a partner at all, so which days
  // carry one is a draw the bake is free to re-roll.
  const PAIRED = {
    word: "\u0B85\u0BA4\u0BBF\u0B95",
    tiles: ["\u0B85", "\u0BA4\u0BBF", "\u0B95"],
    reveal: 0,
    timeLimitSec: 0,
    attempts: 3,
    alsoValid: ["\u0B85\u0B95\u0BA4\u0BBF"],
  };

  const variant =
    new URLSearchParams(window.location.search).get("fixture") === "also-valid"
      ? "also-valid"
      : "solo";
  const payload = variant === "also-valid" ? PAIRED : SOLO;

  const today = new Date().toISOString().slice(0, 10);
  const session: Session = {
    modeId: "harness-anagram",
    packId: "ta-core",
    gameId: "anagram",
    // Scoped by variant as well as by date, so one fixture's saved run can
    // never restore into the other's puzzle.
    sessionId: `harness-anagram-${variant}-${today}`,
    date: today,
    items: [{ gameId: "anagram", payload }],
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

<SessionShell logger={runtime.logger} title="Anagram harness" {progress} bind:stage={stageEl} />

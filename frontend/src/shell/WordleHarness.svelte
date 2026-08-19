<script lang="ts">
  // Row 19 integration harness - the browser proof that the THIRD Game works
  // inside the real runtime: a real Runtime, StorageService, SessionShell and
  // SessionRunner, resolving `wordle` through the PRODUCTION registry (so the
  // lazy code-split loader is exercised, not bypassed). Reached only via
  // `?harness=wordle`.
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

  // A REAL baked payload, lifted from the committed served set through the real
  // generator rather than hand-typed, and escaped like datasets/fixtures/* so
  // the file's own normalization form cannot change what it means.
  //
  // "\u0BAE\u0BC7\u0BB1\u0BCD\u0B95\u0BCB\u0BB3\u0BCD\u0B95\u0BB3\u0BCD"
  // (meeRkooLkaL, quotations) is the fixture because one word carries every
  // property the mechanic has to get right: the mei \u0BB3\u0BCD twice, the
  // two-part matra \u0B95\u0BCB, and three pulli-bearing mei.
  const ANSWERED = {
    word: "\u0BAE\u0BC7\u0BB1\u0BCD\u0B95\u0BCB\u0BB3\u0BCD\u0B95\u0BB3\u0BCD",
    attempts: 8,
    hints: [
      {
        kind: "meaning",
        text:
          "\u0BAA\u0BCA\u0BB0\u0BC1\u0BB3\u0BCD: \u0BB5\u0BC7\u0BB1\u0BCA\u0BB0\u0BC1" +
          "\u0BB5\u0BB0\u0BCD \u0B95\u0BC2\u0BB1\u0BBF\u0BAF\u0BA4\u0BC8\u0B95\u0BCD " +
          "\u0B95\u0BC2\u0BB1\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F \u0BB5\u0B9F\u0BBF" +
          "\u0BB5\u0BA4\u0BCD\u0BA4\u0BBF\u0BB2\u0BC7\u0BAF\u0BC7 \u0B8E\u0B9F\u0BC1" +
          "\u0BA4\u0BCD\u0BA4\u0BC1\u0B95\u0BCD\u0B95\u0BBE\u0B9F\u0BCD\u0B9F\u0BC1\u0BB5\u0BA4\u0BC1",
        cost: 3,
      },
    ],
    meaning:
      "\u0BB5\u0BC7\u0BB1\u0BCA\u0BB0\u0BC1\u0BB5\u0BB0\u0BCD \u0B95\u0BC2\u0BB1\u0BBF" +
      "\u0BAF\u0BA4\u0BC8\u0B95\u0BCD \u0B95\u0BC2\u0BB1\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD" +
      "\u0B9F \u0BB5\u0B9F\u0BBF\u0BB5\u0BA4\u0BCD\u0BA4\u0BBF\u0BB2\u0BC7\u0BAF\u0BC7 " +
      "\u0B8E\u0B9F\u0BC1\u0BA4\u0BCD\u0BA4\u0BC1\u0B95\u0BCD\u0B95\u0BBE\u0B9F\u0BCD" +
      "\u0B9F\u0BC1\u0BB5\u0BA4\u0BC1",
    translationEn: "Citation",
  };

  // The SAME word on a two-attempt budget, reached with `&fixture=short`. The
  // loss path is worth driving in a browser and driving it over eight rows would
  // be forty-eight taps proving the same thing twice; two is the contract's own
  // floor, so this is the shortest legal board rather than a special case.
  const SHORT = { ...ANSWERED, attempts: 2 };

  const variant =
    new URLSearchParams(window.location.search).get("fixture") === "short"
      ? "short"
      : "full";
  const payload = variant === "short" ? SHORT : ANSWERED;

  const today = new Date().toISOString().slice(0, 10);
  const session: Session = {
    modeId: "harness-wordle",
    packId: "ta-core",
    gameId: "wordle",
    // Scoped by variant as well as by date, so one fixture's saved run can never
    // restore into the other's puzzle.
    sessionId: `harness-wordle-${variant}-${today}`,
    date: today,
    items: [{ gameId: "wordle", payload }],
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

<SessionShell logger={runtime.logger} title="Wordle harness" {progress} bind:stage={stageEl} />

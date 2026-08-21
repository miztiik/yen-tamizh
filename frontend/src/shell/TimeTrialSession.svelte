<script lang="ts">
  // The Time Trial screen - the last of the four Modes.
  //
  // It is the Infinite screen with a deadline, and it is built that way on
  // purpose: the same pools, the same ring of Games, the same anti-repeat
  // window, and one extra fact on screen. What it adds is a START and an END.
  //
  // THE RUN OPENS ON A CARD, NOT ON A CLOCK. A countdown that begins while the
  // first board is still being fetched charges the player for the network, so
  // the screen waits to be tapped, then deals the first board, and only THEN
  // starts the clock. Every board after that is dealt against a clock already
  // running - which is the sprint.
  //
  // The clock itself lives in `Countdown` (modes/TimeTrialMode.ts): one rAF
  // loop deriving the remaining time from a monotonic delta. Nothing here
  // schedules a frame or reads a clock, so the header readout and the expiry
  // can never disagree.
  import SessionShell from "./SessionShell.svelte";
  import CountdownHeader from "./CountdownHeader.svelte";
  import Glyph from "../designsystem/Glyph.svelte";
  import { createRuntime } from "../telemetry/runtime";
  import { StorageService } from "../services/StorageService";
  import { SessionRunner, type SessionHost } from "../session/SessionRunner";
  import { GAME_REGISTRY } from "../games/registry";
  import { APP_CONFIG, copyText } from "../lib/config";
  import { todayIso } from "../lib/dates";
  import { InfiniteStream, type StreamStep } from "../modes/InfiniteMode";
  import {
    TIME_TRIAL_MODE_ID,
    Countdown,
    TimeTrialSupply,
    bestRunAt,
    bestRunsWith,
    type BestRun,
  } from "../modes/TimeTrialMode";

  interface Props {
    onHome: () => void;
  }

  let { onHome }: Props = $props();

  const runtime = createRuntime({ dev: import.meta.env.DEV });
  const storage = new StorageService({ store: localStorage });
  const date = todayIso();
  const durationSec = APP_CONFIG.timeTrial.durationSec;
  const durationMs = durationSec * 1000;
  const window_ = APP_CONFIG.infinite.lruWindow;

  type Phase = "ready" | "loading" | "playing" | "over" | "unavailable";

  let phase = $state<Phase>("ready");
  let step = $state<StreamStep | null>(null);
  let remaining = $state(durationMs);
  let solved = $state(0);
  let isNewBest = $state(false);
  let best = $state<BestRun | null>(
    bestRunAt(storage.readBestTimeTrialRuns(), durationSec),
  );
  let stageEl = $state<HTMLElement | undefined>();
  let runner: SessionRunner | null = null;
  let lastDealt: StreamStep | null = null;

  const clock = new Countdown({
    durationMs,
    onTick: (left) => {
      remaining = left;
    },
    onExpire: () => finish(),
  });

  // Plain state, deliberately not a rune: the supply reads it on every deal and
  // no part of the screen renders it, so making it reactive would only invite a
  // component to depend on it.
  let runActive = false;

  // One stream per run: a fresh one on every start, so a second run re-reads the
  // seen window the first one grew rather than continuing from a stale cursor.
  let supply = newSupply();

  function newSupply(): TimeTrialSupply {
    return new TimeTrialSupply(
      new InfiniteStream({
        games: APP_CONFIG.daily.games,
        date,
        difficulty: APP_CONFIG.infinite.defaultDifficulty,
        seen: () => storage.readSeenInfiniteIds(),
      }),
      () => !runActive,
    );
  }

  /** Deal the next board, record it as seen, and hand it to the runner. */
  async function deal(): Promise<boolean> {
    const outcome = await supply.next();
    if (outcome === null) return false; // the run ended while the board was in flight
    if (outcome.status !== "ready") {
      step = null;
      phase = "unavailable";
      return false;
    }
    const dealt = outcome.step;
    storage.markInfiniteSeen(
      {
        date,
        modeId: TIME_TRIAL_MODE_ID,
        gameId: dealt.gameId,
        packId: dealt.session.packId,
      },
      dealt.seenKey,
      window_,
    );
    runner = null;
    step = dealt;
    lastDealt = dealt;
    phase = "playing";
    return true;
  }

  async function begin(): Promise<void> {
    phase = "loading";
    solved = 0;
    isNewBest = false;
    remaining = durationMs;
    runActive = true;
    supply = newSupply();
    if (!(await deal())) {
      runActive = false;
      if (phase === "loading") phase = "unavailable";
      return;
    }
    clock.start();
  }

  /** The deadline passed: stop everything and write the run down. */
  function finish(): void {
    if (phase === "over") return;
    runActive = false;
    clock.stop();
    runner?.exit();
    runner = null;
    step = null;
    remaining = 0;
    phase = "over";

    const context = lastDealt;
    if (context === null) return;
    const run: BestRun = { durationSec, itemsCompleted: solved, achievedOn: date };
    const outcome = bestRunsWith(storage.readBestTimeTrialRuns(), run);
    storage.writeBestTimeTrialRuns(
      {
        date,
        modeId: TIME_TRIAL_MODE_ID,
        gameId: context.gameId,
        packId: context.session.packId,
      },
      outcome.runs,
    );
    isNewBest = outcome.isNewBest;
    best = bestRunAt(outcome.runs, durationSec);
  }

  function leave(): void {
    runActive = false;
    clock.stop();
    runner?.exit();
    onHome();
  }

  // Same mount rule as the Infinite screen: one runner per BOARD, started only
  // once the shell has bound a stage that is actually in the document (the shell
  // is unmounted and remounted between boards).
  $effect(() => {
    const stage = stageEl;
    const current = step;
    if (stage === undefined || !stage.isConnected || current === null || runner !== null) {
      return;
    }
    const host: SessionHost = {
      get stage() {
        return stageEl as HTMLElement;
      },
      setProgress() {
        // A sprint has no "3 of 3"; the clock and the run counter are the only
        // honest progress readings, and both live in the chrome.
      },
      showSummary(result) {
        if (result.itemsCompleted > 0) solved += result.itemsCompleted;
        void deal();
      },
      clearStage() {
        stageEl?.replaceChildren();
      },
    };
    runner = new SessionRunner({
      session: current.session,
      registry: GAME_REGISTRY,
      storage,
      logger: runtime.logger,
      bus: runtime.bus,
      host,
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

{#if phase === "playing" && step}
  <SessionShell
    logger={runtime.logger}
    title={copyText("mode-time-trial-title")}
    backLabel={copyText("action-home")}
    settingsLabel={copyText("action-settings")}
    bind:stage={stageEl}
    onExit={leave}
  >
    {#snippet headerAside()}
      <CountdownHeader
        remainingMs={remaining}
        {durationMs}
        label={copyText("time-trial-remaining")}
      />
    {/snippet}
    {#snippet rail()}
      {#if step}
        <p
          class="font-tamil text-sm font-semibold text-text-secondary"
          data-testid="time-trial-game-name"
          data-game={step.gameId}
          data-item={step.seenKey}
        >
          {copyText(`game-${step.gameId}-title`)}
        </p>
      {/if}
      <p class="font-tamil text-sm text-text-tertiary" data-testid="time-trial-solved">
        {copyText("summary-solved")}
        <span class="font-mono text-text-primary">{solved}</span>
      </p>
    {/snippet}
  </SessionShell>
{:else if phase === "over"}
  <main
    class="flex min-h-dvh flex-col items-center justify-center gap-md p-lg text-center"
    data-testid="time-trial-over"
  >
    <h1 class="font-tamil text-xl font-semibold text-text-primary">
      {copyText("time-trial-over-title")}
    </h1>
    <p class="font-tamil text-text-secondary">
      {copyText("summary-solved")}
      <span class="ml-xs font-mono text-3xl font-bold text-accent" data-testid="time-trial-score">
        {solved}
      </span>
    </p>
    {#if isNewBest}
      <p
        class="inline-flex items-center gap-xs rounded-full bg-bg-elevated px-md py-xs font-tamil text-sm text-success"
        data-testid="time-trial-new-best"
      >
        <Glyph id="star" />
        {copyText("time-trial-new-best")}
      </p>
    {/if}
    {#if best}
      <p class="font-tamil text-sm text-text-tertiary" data-testid="time-trial-best">
        {copyText("time-trial-best")}
        <span class="font-mono text-text-secondary">{best.itemsCompleted}</span>
      </p>
    {/if}
    <div class="flex flex-wrap items-center justify-center gap-sm">
      <button
        type="button"
        class="inline-flex items-center gap-xs rounded-lg bg-accent px-lg py-md font-tamil text-bg transition-transform duration-fast ease-spring hover:-translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        data-testid="time-trial-again"
        onclick={() => void begin()}
      >
        <Glyph id="timer" />
        {copyText("time-trial-again")}
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-xs rounded-lg border border-border px-lg py-md font-tamil text-text-primary transition-colors duration-fast ease-smooth hover:bg-bg-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        onclick={onHome}
      >
        <Glyph id="back" />
        {copyText("action-home")}
      </button>
    </div>
  </main>
{:else if phase === "unavailable"}
  <main
    class="flex min-h-dvh flex-col items-center justify-center gap-md p-lg text-center"
    data-testid="time-trial-unavailable"
  >
    <h1 class="font-tamil text-xl font-semibold text-text-primary">
      {copyText("time-trial-empty-title")}
    </h1>
    <p class="max-w-xs font-tamil text-text-secondary">{copyText("time-trial-empty-body")}</p>
    <button
      type="button"
      class="inline-flex items-center gap-xs rounded-lg border border-border px-lg py-md font-tamil text-text-primary transition-colors duration-fast ease-smooth hover:bg-bg-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      onclick={onHome}
    >
      <Glyph id="back" />
      {copyText("action-home")}
    </button>
  </main>
{:else if phase === "loading"}
  <main
    class="flex min-h-dvh items-center justify-center p-lg"
    data-testid="time-trial-loading"
    aria-busy="true"
  >
    <p class="anim-shimmer font-tamil text-text-secondary">{copyText("daily-loading")}</p>
  </main>
{:else}
  <main
    class="mx-auto flex min-h-dvh w-full max-w-md flex-col items-center justify-center gap-md p-lg text-center"
    data-testid="time-trial-ready"
  >
    <Glyph id="timer" size="2.5rem" class="text-accent" />
    <h1 class="font-tamil text-2xl font-semibold text-text-primary">
      {copyText("mode-time-trial-title")}
    </h1>
    <p class="font-tamil text-text-secondary">
      {copyText("time-trial-duration")}
      <span class="ml-xs font-mono text-text-primary">{durationSec}</span>
      {copyText("time-trial-seconds")}
    </p>
    {#if best}
      <p class="font-tamil text-sm text-text-tertiary" data-testid="time-trial-best">
        {copyText("time-trial-best")}
        <span class="font-mono text-text-secondary">{best.itemsCompleted}</span>
      </p>
    {/if}
    <button
      type="button"
      class="mt-sm inline-flex items-center gap-xs rounded-lg bg-accent px-xl py-md font-tamil text-lg text-bg shadow-sm transition-transform duration-fast ease-spring hover:-translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      data-testid="time-trial-start"
      onclick={() => void begin()}
    >
      {copyText("time-trial-start")}
    </button>
    <button
      type="button"
      class="inline-flex items-center gap-xs rounded-lg px-lg py-md font-tamil text-text-secondary transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      data-testid="time-trial-home"
      onclick={onHome}
    >
      <Glyph id="back" />
      {copyText("action-home")}
    </button>
  </main>
{/if}

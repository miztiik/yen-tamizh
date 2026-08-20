<script lang="ts">
  // The Daily session screen - the Home's one tap turns into a played puzzle.
  //
  // It wires the real runtime (Row 11) to the real bank (Row 13): DailyMode
  // loads the day, the SessionRunner walks its items, and the Game mounts into
  // the shell's stage. This component owns only the framing a Mode cannot: the
  // loading, unavailable, and finished screens.
  //
  // The streak ticks HERE, once, when the day is completed - not inside the
  // Game (which must never see storage) and not per item (Palm: a day is the
  // unit of a streak). StorageService keeps it idempotent, so re-opening a
  // finished day never inflates the run.
  import SessionShell from "../shell/SessionShell.svelte";
  import Glyph from "../designsystem/Glyph.svelte";
  import { createRuntime } from "../telemetry/runtime";
  import { StorageService } from "../services/StorageService";
  import { SessionRunner, type SessionHost } from "../session/SessionRunner";
  import { GAME_REGISTRY } from "../games/registry";
  import type { Session, SessionResult } from "../session/types";
  import { copyText } from "../lib/config";
  import { todayIso } from "../lib/dates";
  import { DAILY_MODE_ID, loadDailySession, type DailyOutcome } from "../modes/DailyMode";

  interface Props {
    onHome: () => void;
  }

  let { onHome }: Props = $props();

  const runtime = createRuntime({ dev: import.meta.env.DEV });
  const storage = new StorageService({ store: localStorage });
  const logger = runtime.logger.child(DAILY_MODE_ID, { modeId: DAILY_MODE_ID });

  type Phase = "loading" | "playing" | "unavailable" | "done";

  let phase = $state<Phase>("loading");
  let outcome = $state<DailyOutcome | null>(null);
  let progress = $state<{ completed: number; total: number } | null>(null);
  let summary = $state<{ result: SessionResult; streak: number } | null>(null);
  let stageEl = $state<HTMLElement | undefined>();
  // Reactive because the rail reads it: the Game's name and the day's theme are
  // drawn from the loaded session, not from the outcome.
  let session = $state<Session | null>(null);
  let runner: SessionRunner | null = null;
  let started = false;

  // A day holds three DIFFERENT Games, so the rail names the board the player
  // is on - one word, in the same slot every time. `progress.completed` is the
  // index of the item being played, and it runs one past the last item at the
  // end of the day, which is why an absent name renders nothing at all.
  const currentGame = $derived(
    progress === null ? undefined : session?.items[progress.completed]?.gameId,
  );

  void (async () => {
    const loaded = await loadDailySession({ today: todayIso() });
    outcome = loaded;
    if (loaded.status === "ready") {
      session = loaded.session;
      phase = "playing";
    } else {
      phase = "unavailable";
    }
  })();

  function finish(result: SessionResult): void {
    const current = session;
    if (current === null) return;
    const tick = storage.tickStreak({
      date: current.date,
      modeId: current.modeId,
      gameId: current.gameId,
      packId: current.packId,
    });
    if (tick.ticked) {
      logger.emit("streak.updated", {
        data: { before: tick.before, after: tick.after },
      });
    }
    summary = { result, streak: tick.after };
    phase = "done";
  }

  // The runner mounts Games into the shell's stage, so it can only start once
  // the shell has bound that element - and only once per session.
  $effect(() => {
    const stage = stageEl;
    const current = session;
    if (stage === undefined || current === null || started) return;
    started = true;
    const host: SessionHost = {
      get stage() {
        return stageEl as HTMLElement;
      },
      setProgress(completed, total) {
        progress = { completed, total };
      },
      showSummary(result) {
        finish(result);
      },
      clearStage() {
        stageEl?.replaceChildren();
      },
    };
    runner = new SessionRunner({
      session: current,
      registry: GAME_REGISTRY,
      storage,
      logger: runtime.logger,
      bus: runtime.bus,
      host,
      // The Mode hands the Game its player-facing wording; the Game never reads
      // the copy map itself (docs/concepts/ui-shell.md - a Game sees only its
      // payload and its context).
      config: { labels: { alsoValid: copyText("anagram-also-valid") } },
    });
    void runner.start();
  });

  function leave(): void {
    runner?.exit();
    onHome();
  }
</script>

{#if phase === "playing"}
  <SessionShell
    logger={runtime.logger}
    title={copyText("mode-daily-title")}
    backLabel={copyText("action-home")}
    settingsLabel={copyText("action-settings")}
    {progress}
    bind:stage={stageEl}
    onExit={leave}
  >
    {#snippet rail()}
      {#if currentGame !== undefined}
        <p
          class="font-tamil text-sm font-semibold text-text-secondary"
          data-testid="daily-game-name"
        >
          {copyText(`game-${currentGame}-title`)}
        </p>
      {/if}
      {#if session?.theme !== undefined}
        <p class="font-tamil text-sm text-text-tertiary" data-testid="daily-theme">
          {copyText("daily-theme-label")}: {copyText(session.theme)}
        </p>
      {/if}
      {#if outcome?.status === "ready" && !outcome.isToday}
        <p class="font-tamil text-sm text-text-tertiary" data-testid="daily-older-day">
          {copyText("daily-older-day")}: {outcome.date}
        </p>
      {/if}
    {/snippet}
  </SessionShell>
{:else if phase === "done" && summary}
  <main
    class="flex min-h-dvh flex-col items-center justify-center gap-lg p-lg text-center"
    data-testid="session-summary"
  >
    <Glyph id="check" size="3rem" class="anim-pop text-success" title={copyText("summary-title")} />
    <h1 class="font-tamil text-2xl font-bold text-text-primary">{copyText("summary-title")}</h1>
    <dl class="flex items-start justify-center gap-xl">
      <div class="flex flex-col gap-xs">
        <dt class="font-tamil text-sm text-text-secondary">{copyText("summary-score")}</dt>
        <dd class="font-mono text-2xl text-text-primary" data-testid="summary-score">
          {summary.result.totalScore}
        </dd>
      </div>
      <div class="flex flex-col gap-xs">
        <dt class="font-tamil text-sm text-text-secondary">{copyText("summary-solved")}</dt>
        <dd class="font-mono text-2xl text-text-primary">
          {summary.result.itemsCompleted}/{summary.result.itemsTotal}
        </dd>
      </div>
      <div class="flex flex-col gap-xs">
        <dt class="font-tamil text-sm text-text-secondary">{copyText("summary-streak")}</dt>
        <dd class="font-mono text-2xl text-warning" data-testid="summary-streak">
          {summary.streak}
        </dd>
      </div>
    </dl>
    <!-- The dwell content sits LAST, above the exit: the stats are the glance
         and hold the screenshot, the words are what the player stays to read.
         A word with nothing to say renders alone - an empty slot would
         advertise a hole in the data - and a word that was LOST still shows its
         meaning, or losing it would punish twice. -->
    {#if summary.result.items.length > 0}
      <ul class="flex w-full max-w-xs flex-col gap-md text-left" data-testid="summary-words">
        {#each summary.result.items as item, index (index)}
          <li class="flex flex-col gap-xs" data-testid="summary-word" data-solved={item.solved}>
            <span class="font-tamil text-xl font-semibold text-text-primary">{item.word}</span>
            {#if item.meaning}
              <span class="font-tamil text-base text-text-secondary">{item.meaning}</span>
            {/if}
            {#if item.translationEn}
              <span class="font-display text-base text-text-tertiary" lang="en"
                >{item.translationEn}</span
              >
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
    <button
      type="button"
      class="inline-flex items-center gap-xs rounded-lg bg-accent px-lg py-md font-tamil text-bg shadow-sm transition-transform duration-fast ease-spring hover:-translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      data-testid="summary-home"
      onclick={onHome}
    >
      <Glyph id="back" />
      {copyText("action-home")}
    </button>
  </main>
{:else if phase === "unavailable"}
  <main
    class="flex min-h-dvh flex-col items-center justify-center gap-md p-lg text-center"
    data-testid="daily-unavailable"
  >
    <h1 class="font-tamil text-xl font-semibold text-text-primary">
      {copyText("daily-empty-title")}
    </h1>
    <p class="max-w-xs font-tamil text-text-secondary">{copyText("daily-empty-body")}</p>
    <button
      type="button"
      class="inline-flex items-center gap-xs rounded-lg border border-border px-lg py-md font-tamil text-text-primary transition-colors duration-fast ease-smooth hover:bg-bg-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      onclick={onHome}
    >
      <Glyph id="back" />
      {copyText("action-home")}
    </button>
  </main>
{:else}
  <main
    class="flex min-h-dvh items-center justify-center p-lg"
    data-testid="daily-loading"
    aria-busy="true"
  >
    <p class="anim-shimmer font-tamil text-text-secondary">{copyText("daily-loading")}</p>
  </main>
{/if}

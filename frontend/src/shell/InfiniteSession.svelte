<script lang="ts">
  // The Infinite screen - one tap from the Home into a stream that does not end.
  //
  // It wires the real runtime (Row 11) to the pre-generated pool (Row 22):
  // InfiniteStream reads one Game's index, picks a board the anti-repeat window
  // has not seen, and the SessionRunner plays that single board. When the board
  // is done the stream deals the next one, from the next Game in the ring, and
  // the screen never returns to a menu - that is the whole Mode.
  //
  // A board is recorded as SEEN the moment it is dealt, not when it is solved,
  // and it is recorded HERE - never inside the Game, which may not touch
  // storage. StorageService keeps the list an LRU bounded by the config'd
  // window, so a player who never stops does not grow their save without limit.
  import SessionShell from "./SessionShell.svelte";
  import Glyph from "../designsystem/Glyph.svelte";
  import { createRuntime } from "../telemetry/runtime";
  import { StorageService } from "../services/StorageService";
  import { SessionRunner, type SessionHost } from "../session/SessionRunner";
  import { GAME_REGISTRY } from "../games/registry";
  import { APP_CONFIG, copyText } from "../lib/config";
  import { todayIso } from "../lib/dates";
  import {
    INFINITE_MODE_ID,
    InfiniteStream,
    type StreamStep,
  } from "../modes/InfiniteMode";

  interface Props {
    onHome: () => void;
  }

  let { onHome }: Props = $props();

  const runtime = createRuntime({ dev: import.meta.env.DEV });
  const storage = new StorageService({ store: localStorage });
  const date = todayIso();
  const window_ = APP_CONFIG.infinite.lruWindow;
  // The bands come from the Games' own registry through the pool index, but the
  // chooser has to draw them before any index is loaded, so it draws the three
  // the generator declares. They are slugs; the label beside each is copy.
  const BANDS = ["easy", "medium", "hard"] as const;

  type Phase = "loading" | "playing" | "unavailable";

  let phase = $state<Phase>("loading");
  let step = $state<StreamStep | null>(null);
  let difficulty = $state(APP_CONFIG.infinite.defaultDifficulty);
  let solved = $state(0);
  let stageEl = $state<HTMLElement | undefined>();
  let runner: SessionRunner | null = null;

  const stream = new InfiniteStream({
    games: APP_CONFIG.daily.games,
    date,
    // The config value rather than the rune: this is the stream's STARTING
    // filter, and every later change goes through `choose` -> setDifficulty.
    difficulty: APP_CONFIG.infinite.defaultDifficulty,
    seen: () => storage.readSeenInfiniteIds(),
  });

  /** Deal the next board, record it as seen, and hand it to the runner. */
  async function deal(): Promise<void> {
    phase = "loading";
    const outcome = await stream.next();
    if (outcome.status !== "ready") {
      step = null;
      phase = "unavailable";
      return;
    }
    const dealt = outcome.step;
    storage.markInfiniteSeen(
      {
        date,
        modeId: INFINITE_MODE_ID,
        gameId: dealt.gameId,
        packId: dealt.session.packId,
      },
      dealt.seenKey,
      window_,
    );
    runner = null;
    step = dealt;
    phase = "playing";
  }

  void deal();

  function choose(band: string): void {
    if (band === difficulty) return;
    difficulty = band;
    stream.setDifficulty(band);
    runner?.exit();
    void deal();
  }

  function leave(): void {
    runner?.exit();
    onHome();
  }

  // The runner mounts a Game into the shell's stage, so it can only start once
  // the shell has bound that element - and only once per BOARD, which is what
  // makes each board a fresh session rather than a resumed one. The connected
  // check is what keeps a board off the PREVIOUS stage: the shell is unmounted
  // and remounted between boards, and the bound element is only replaced once
  // the new one exists.
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
        // A stream has no "3 of 3"; the run counter in the rail is the honest
        // progress reading, and it is updated when a board is finished.
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
      // The Mode hands the Game its player-facing wording; the Game never reads
      // the copy map itself (docs/concepts/ui-shell.md).
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
    title={copyText("mode-infinite-title")}
    backLabel={copyText("action-home")}
    settingsLabel={copyText("action-settings")}
    bind:stage={stageEl}
    onExit={leave}
  >
    {#snippet rail()}
      <!-- The snippet does not inherit the block's narrowing, so the board is
           re-checked here rather than asserted non-null. -->
      {#if step}
        <p
          class="font-tamil text-sm font-semibold text-text-secondary"
          data-testid="infinite-game-name"
          data-game={step.gameId}
          data-item={step.seenKey}
        >
          {copyText(`game-${step.gameId}-title`)}
        </p>
      {/if}
      <p class="font-tamil text-sm text-text-tertiary" data-testid="infinite-solved">
        {copyText("infinite-solved")}
        <span class="font-mono text-text-primary">{solved}</span>
      </p>
      <!-- The difficulty chooser is the one control an endless stream needs:
           there is no day to set the curve, so the player sets it. -->
      <div
        class="flex gap-xs"
        role="group"
        aria-label={copyText("infinite-difficulty-label")}
        data-testid="infinite-difficulty"
      >
        {#each BANDS as band (band)}
          <button
            type="button"
            class="rounded-md border border-border px-sm py-xs font-tamil text-xs transition-colors duration-fast ease-smooth focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent {band ===
            difficulty
              ? 'bg-accent text-bg'
              : 'text-text-secondary hover:bg-bg-elevated'}"
            data-testid="infinite-band"
            data-band={band}
            aria-pressed={band === difficulty}
            onclick={() => choose(band)}
          >
            {copyText(`difficulty-${band}`)}
          </button>
        {/each}
      </div>
    {/snippet}
  </SessionShell>
{:else if phase === "unavailable"}
  <main
    class="flex min-h-dvh flex-col items-center justify-center gap-md p-lg text-center"
    data-testid="infinite-unavailable"
  >
    <h1 class="font-tamil text-xl font-semibold text-text-primary">
      {copyText("infinite-empty-title")}
    </h1>
    <p class="max-w-xs font-tamil text-text-secondary">{copyText("infinite-empty-body")}</p>
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
    data-testid="infinite-loading"
    aria-busy="true"
  >
    <p class="anim-shimmer font-tamil text-text-secondary">{copyText("daily-loading")}</p>
  </main>
{/if}

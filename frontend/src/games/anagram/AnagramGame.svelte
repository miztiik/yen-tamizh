<script lang="ts">
  // The anagram playing surface - the FIRST playable Game (docs/concepts/
  // games.md `anagram`). One verb: tap the ezhuthu tiles in order to spell the
  // word (Palm worldview #1). There is deliberately NO "check" button - the
  // arrangement auto-submits the moment the last slot fills, so the mechanic
  // teaches itself in the first few seconds with nothing to read (Palm #2/#10,
  // Player #1).
  //
  // This component is a thin projection of `logic.ts`: every rule (scramble,
  // solve, score, attempts, hints, key mapping) is a pure function there, so the
  // mechanic is unit-tested in node while this file only renders and reacts.
  //
  // It reads ONLY its `payload` and the injected `GameContext` pieces (logger,
  // config slice, clock). It imports no app config, no storage, and no telemetry
  // singleton - the boundary the Oracle in `boundary.test.ts` enforces (Fowler).
  import { tick, untrack } from "svelte";

  import Glyph from "../../designsystem/Glyph.svelte";
  import type { GameContext } from "../../session/types";

  import {
    attemptsRemaining,
    buildTray,
    clearPlaced,
    initialState,
    isFull,
    keyToAction,
    normalizeState,
    nextHint,
    placeTile,
    placedEzhuthu,
    remainingTiles,
    removeTile,
    resolveLabels,
    revealNextHint,
    revealedHints,
    submitAttempt,
    targetEzhuthu,
    undoLast,
    type AnagramPayload,
    type AnagramState,
  } from "./logic";

  interface Props {
    payload: AnagramPayload;
    logger: GameContext["logger"];
    config: GameContext["config"];
    now: GameContext["now"];
  }

  let { payload, logger, config, now }: Props = $props();

  // A Game instance is built fresh per session item, so the payload and the
  // context never change under it. The one-time setup therefore reads them
  // untracked: the scramble is seeded from the word, so neither a re-render nor
  // a resume ever reshuffles the tray under the player's thumb.
  const setup = untrack(() => {
    const clusters = targetEzhuthu(payload);
    const celebration = config.winCelebrationMs;
    return {
      tray: buildTray(payload),
      target: clusters,
      labels: resolveLabels(config),
      revealCount: Math.min(payload.reveal ?? 0, clusters.length),
      // The celebration beat: the win stays on screen for a moment before the
      // runner is told and clears the stage (Palm - the win moment is the
      // reward; Player - it has to be worth a screenshot). A knob with a default.
      celebrationMs: typeof celebration === "number" ? celebration : 900,
      // Elapsed is measured from this mount (telemetry only - the score is base
      // minus hint cost). Time pressure belongs to the Mode's session clock, not
      // to the mechanic, so this Game ships no countdown.
      startedAt: now(),
    };
  });
  const { tray, target, labels, revealCount, celebrationMs, startedAt } = setup;

  let gameState = $state<AnagramState>(initialState());
  let feedback = $state<{ tone: "success" | "danger"; text: string } | null>(null);
  // Bumped on every miss so the shake keyframe re-runs on a repeat wrong answer.
  let shakeToken = $state(0);

  let reported = false;
  let celebrationTimer: ReturnType<typeof setTimeout> | null = null;
  let trayEl: HTMLElement | undefined = $state();
  let slotsEl: HTMLElement | undefined = $state();

  const placed = $derived(placedEzhuthu(tray, gameState));
  const trayTiles = $derived(remainingTiles(tray, gameState));
  const shownHints = $derived(revealedHints(payload, gameState));
  const hintLeft = $derived(nextHint(payload, gameState) !== null);
  const attemptsLeft = $derived(attemptsRemaining(payload, gameState));

  untrack(() =>
    logger.emit("puzzle.started", {
      data: { word: payload.word, tiles: payload.tiles.length, attempts: payload.attempts },
    }),
  );

  /** Serialize for the runner (GameModule.getState). */
  export function getState(): AnagramState {
    return { ...gameState, placedTileIds: [...gameState.placedTileIds] };
  }

  /** Rehydrate a persisted snapshot (GameModule.restoreState). */
  export function restoreState(raw: unknown): void {
    gameState = normalizeState(raw);
    if (!gameState.finished) return;
    // A reload during the celebration must not strand the session: report the
    // already-decided outcome instead of replaying the beat. It is deferred to a
    // microtask so the runner finishes mounting before it hears about it.
    if (gameState.solved) {
      feedback = { tone: "success", text: `${labels.correct} +${gameState.score}` };
      queueMicrotask(() =>
        report("puzzle.completed", { score: gameState.score, attempts: gameState.attempts }),
      );
    } else {
      feedback = { tone: "danger", text: `${labels.outOfAttempts} - ${payload.word}` };
      queueMicrotask(() => report("puzzle.abandoned", { reason: "attempts-exhausted" }));
    }
  }

  /** Release the pending celebration timer when the runner tears the Game down. */
  export function dispose(): void {
    if (celebrationTimer !== null) {
      clearTimeout(celebrationTimer);
      celebrationTimer = null;
    }
  }

  function elapsedMs(): number {
    return Math.max(0, now() - startedAt);
  }

  function report(name: "puzzle.completed" | "puzzle.abandoned", data: Record<string, unknown>): void {
    if (reported) return;
    reported = true;
    logger.emit(name, {
      level: name === "puzzle.abandoned" ? "warn" : "info",
      data: { ...data, elapsedMs: elapsedMs() },
    });
  }

  function reportAfterBeat(
    name: "puzzle.completed" | "puzzle.abandoned",
    data: Record<string, unknown>,
  ): void {
    if (celebrationMs <= 0) {
      report(name, data);
      return;
    }
    celebrationTimer = setTimeout(() => {
      celebrationTimer = null;
      report(name, data);
    }, celebrationMs);
  }

  function submit(): void {
    const outcome = submitAttempt(payload, tray, gameState, config);
    gameState = outcome.state;

    logger.emit("puzzle.attempt.submitted", {
      data: {
        attemptIndex: outcome.attemptIndex,
        attempt: outcome.attempt,
        correct: outcome.correct,
        elapsedMs: elapsedMs(),
      },
    });

    if (outcome.correct) {
      feedback = { tone: "success", text: `${labels.correct} +${gameState.score}` };
      reportAfterBeat("puzzle.completed", {
        score: gameState.score,
        attempts: gameState.attempts,
      });
      return;
    }

    shakeToken += 1;
    if (outcome.exhausted) {
      feedback = { tone: "danger", text: `${labels.outOfAttempts} - ${payload.word}` };
      reportAfterBeat("puzzle.abandoned", { reason: "attempts-exhausted" });
      return;
    }
    feedback = { tone: "danger", text: `${labels.wrong} - ${labels.attemptsLeft} ${attemptsLeft}` };
  }

  function place(tileId: string): void {
    if (gameState.finished) return;
    const next = placeTile(payload, gameState, tileId);
    if (next === gameState) return;
    gameState = next;
    feedback = null;
    if (isFull(payload, gameState)) submit();
  }

  function unplace(tileId: string): void {
    gameState = removeTile(gameState, tileId);
    feedback = null;
  }

  function undo(): void {
    gameState = undoLast(gameState);
    feedback = null;
  }

  function clear(): void {
    gameState = clearPlaced(gameState);
    feedback = null;
  }

  function onTileKey(event: KeyboardEvent, tileId: string): void {
    const action = keyToAction(event.key);
    if (action === null) return;
    // Handle placement here rather than letting the button synthesize a click,
    // so Enter and Space cannot place the same tile twice.
    event.preventDefault();
    if (action === "place") place(tileId);
    else if (action === "undo") undo();
    else clear();
    void keepFocusInPlay();
  }

  function onSlotKey(event: KeyboardEvent, tileId: string): void {
    const action = keyToAction(event.key);
    if (action === null) return;
    event.preventDefault();
    if (action === "clear") clear();
    else unplace(tileId);
    void keepFocusInPlay();
  }

  /**
   * A placement removes the focused tile from the tray, which would drop focus
   * to the document body and strand a keyboard player. Move it to the next tile
   * (or, on the last one, to the arrangement) so play continues without Tab.
   */
  async function keepFocusInPlay(): Promise<void> {
    await tick();
    const next =
      trayEl?.querySelector("button") ?? slotsEl?.querySelector("button:not([disabled])");
    next?.focus();
  }

  function useHint(): void {
    const hint = nextHint(payload, gameState);
    if (hint === null) return;
    gameState = revealNextHint(payload, gameState);
    logger.emit("puzzle.hint.used", { data: { kind: hint.kind, cost: hint.cost } });
  }
</script>

<section
  class="mx-auto flex min-h-full w-full max-w-md flex-col justify-center gap-lg"
  data-testid="anagram-game"
  aria-label={labels.prompt}
>
  <header class="flex items-baseline justify-between gap-sm">
    <h2 class="font-display text-lg font-semibold text-text-primary">{labels.prompt}</h2>
    {#if !gameState.finished}
      <p class="font-mono text-text-secondary" data-testid="anagram-attempts">
        {labels.attemptsLeft}
        {attemptsLeft}
      </p>
    {/if}
  </header>

  {#key shakeToken}
    <div
      class="flex flex-wrap justify-center gap-sm"
      class:anim-shake={shakeToken > 0 && !gameState.solved}
      class:anim-victory={gameState.solved}
      bind:this={slotsEl}
      role="group"
      aria-label={labels.answer}
      data-testid="anagram-slots"
    >
      {#each target as cluster, index (index)}
        {@const tileId = gameState.placedTileIds[index]}
        {@const ezhuthu = placed[index] ?? ""}
        {#if tileId !== undefined}
          <button
            type="button"
            class="flex h-14 w-14 items-center justify-center rounded-md border border-accent bg-bg-elevated font-tamil text-2xl text-text-primary shadow-sm transition-transform duration-fast ease-spring hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
            class:border-success={gameState.solved}
            class:bg-tile-correct={gameState.solved}
            data-testid="anagram-slot"
            aria-label={`${labels.placedSlot} ${index + 1}: ${ezhuthu}`}
            disabled={gameState.finished}
            onclick={() => unplace(tileId)}
            onkeydown={(event) => onSlotKey(event, tileId)}
          >
            {ezhuthu}
          </button>
        {:else}
          <div
            class="flex h-14 w-14 items-center justify-center rounded-md border-2 border-dashed border-text-tertiary bg-bg font-tamil text-2xl text-text-tertiary"
            data-testid="anagram-slot"
            aria-label={`${labels.slot} ${index + 1}`}
          >
            {index < revealCount ? cluster : ""}
          </div>
        {/if}
      {/each}
    </div>
  {/key}

  <p
    class="min-h-6 text-center font-display"
    class:anim-pop={feedback !== null}
    class:text-success={feedback?.tone === "success"}
    class:text-danger={feedback?.tone === "danger"}
    data-testid="anagram-feedback"
    role="status"
    aria-live="polite"
  >
    {#if feedback}
      {#if feedback.tone === "success"}
        <Glyph id="check" class="mr-xs inline-block align-text-bottom" />
      {/if}{feedback.text}
    {/if}
  </p>

  <div
    class="flex flex-wrap justify-center gap-sm"
    bind:this={trayEl}
    role="group"
    aria-label={labels.tray}
    data-testid="anagram-tray"
  >
    {#each trayTiles as tile (tile.id)}
      <button
        type="button"
        class="anim-pop flex h-14 w-14 items-center justify-center rounded-md border border-border bg-bg-elevated font-tamil text-2xl text-text-primary shadow-md transition-transform duration-fast ease-spring hover:-translate-y-1 active:translate-y-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        data-testid="anagram-tile"
        data-tile-id={tile.id}
        aria-label={`${labels.trayTile}: ${tile.ezhuthu}`}
        disabled={gameState.finished}
        onclick={() => place(tile.id)}
        onkeydown={(event) => onTileKey(event, tile.id)}
      >
        {tile.ezhuthu}
      </button>
    {/each}
  </div>

  {#if (payload.hints ?? []).length > 0}
    <div class="flex flex-col items-center gap-sm">
      <button
        type="button"
        class="inline-flex items-center gap-xs rounded-md border border-border bg-bg-elevated px-md py-sm text-text-secondary shadow-sm transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        data-testid="anagram-hint"
        disabled={!hintLeft || gameState.finished}
        onclick={useHint}
      >
        <Glyph id="hint" />
        {hintLeft ? labels.hint : labels.hintsSpent}
      </button>

      {#if shownHints.length > 0}
        <ul class="flex flex-wrap justify-center gap-xs" data-testid="anagram-hint-list">
          {#each shownHints as hint, index (index)}
            <li
              class="anim-toast-in inline-flex items-center gap-xs rounded-full bg-bg-elevated px-md py-xs text-text-secondary shadow-sm"
            >
              <span class="font-tamil">{hint.text}</span>
              <span class="font-mono text-warning">-{hint.cost}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</section>

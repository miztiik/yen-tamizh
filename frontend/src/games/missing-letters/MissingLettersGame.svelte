<script lang="ts">
  // The missing-letters playing surface (docs/concepts/games.md
  // `missing-letters`). One verb: tap an ezhuthu from the bank to drop it into
  // the hole (Palm worldview #1). The word is on screen with a gap in it, so
  // there is nothing to read before the first move - the board states the rule
  // by looking the way it does (Palm #2/#10, Player #1). There is deliberately
  // NO "check" button: the board auto-submits the moment the last hole fills.
  //
  // This component is a thin projection of `logic.ts`: every rule (which cells
  // are holes, solve, score, attempts, hints, key mapping) is a pure function
  // there, so the mechanic is unit-tested in node while this file only renders
  // and reacts.
  //
  // It reads ONLY its `payload` and the injected `GameContext` pieces (logger,
  // config slice, clock). It imports no app config, no storage, and no telemetry
  // singleton - the boundary the Oracle in `boundary.test.ts` enforces (Fowler).
  import { tick, untrack } from "svelte";

  import Glyph from "../../designsystem/Glyph.svelte";
  import type { GameContext } from "../../session/types";

  import {
    attemptsRemaining,
    buildChoices,
    cells,
    clearBlank,
    clearFilled,
    fillNextBlank,
    initialState,
    isFull,
    keyToAction,
    nextHint,
    normalizeState,
    remainingChoices,
    resolveLabels,
    revealNextHint,
    revealedHints,
    submitAttempt,
    undoLast,
    type MissingLettersPayload,
    type MissingLettersState,
  } from "./logic";

  interface Props {
    payload: MissingLettersPayload;
    logger: GameContext["logger"];
    config: GameContext["config"];
    now: GameContext["now"];
  }

  let { payload, logger, config, now }: Props = $props();

  // A Game instance is built fresh per session item, so the payload and the
  // context never change under it. The one-time setup therefore reads them
  // untracked: the bank arrives already ordered by the bake, so neither a
  // re-render nor a resume ever reshuffles it under the player's thumb.
  const setup = untrack(() => {
    const celebration = config.winCelebrationMs;
    return {
      choices: buildChoices(payload),
      labels: resolveLabels(config),
      // The celebration beat: the win stays on screen for a moment before the
      // runner is told and clears the stage (Palm - the win moment is the
      // reward). A knob with a default.
      celebrationMs: typeof celebration === "number" ? celebration : 900,
      // Elapsed is measured from this mount (telemetry only - the score is base
      // minus hint cost). Time pressure belongs to the Mode's session clock, not
      // to the mechanic, so this Game ships no countdown.
      startedAt: now(),
    };
  });
  const { choices, labels, celebrationMs, startedAt } = setup;

  let gameState = $state<MissingLettersState>(initialState());
  // Three tones, not two: a miss that is a REAL served word is neither a win nor
  // a rejection, so it gets its own tone (warning + a flip that reads as
  // reappraisal) rather than being flattened into "wrong".
  type Feedback = { tone: "success" | "warning" | "danger"; text: string };
  let feedback = $state<Feedback | null>(null);
  // Bumped on every message so its animation re-runs even when the text repeats.
  let feedbackToken = $state(0);
  // Bumped on every REJECTED miss so the shake keyframe re-runs. An alternative
  // word never bumps it: a shake there would read as rejection.
  let shakeToken = $state(0);

  let reported = false;
  let celebrationTimer: ReturnType<typeof setTimeout> | null = null;
  let bankEl: HTMLElement | undefined = $state();
  let wordEl: HTMLElement | undefined = $state();

  const board = $derived(cells(payload, choices, gameState));
  const bank = $derived(remainingChoices(choices, gameState));
  const shownHints = $derived(revealedHints(payload, gameState));
  const pendingHint = $derived(nextHint(payload, gameState));
  const attemptsLeft = $derived(attemptsRemaining(payload, gameState));

  function setFeedback(next: Feedback | null): void {
    feedback = next;
    feedbackToken += 1;
  }

  untrack(() =>
    logger.emit("puzzle.started", {
      data: {
        word: payload.word,
        blanks: payload.blanks.length,
        choices: payload.choices.length,
        attempts: payload.attempts,
      },
    }),
  );

  /** Serialize for the runner (GameModule.getState). */
  export function getState(): MissingLettersState {
    return { ...gameState, filledChoiceIds: [...gameState.filledChoiceIds] };
  }

  /** Rehydrate a persisted snapshot (GameModule.restoreState). */
  export function restoreState(raw: unknown): void {
    gameState = normalizeState(raw);
    if (!gameState.finished) return;
    // A reload during the celebration must not strand the session: report the
    // already-decided outcome instead of replaying the beat. It is deferred to a
    // microtask so the runner finishes mounting before it hears about it.
    if (gameState.solved) {
      setFeedback({ tone: "success", text: `${labels.correct} +${gameState.score}` });
      queueMicrotask(() =>
        report("puzzle.completed", { score: gameState.score, attempts: gameState.attempts }),
      );
    } else {
      setFeedback({ tone: "danger", text: `${labels.outOfAttempts} - ${payload.word}` });
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

  function report(
    name: "puzzle.completed" | "puzzle.abandoned",
    data: Record<string, unknown>,
  ): void {
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
    const outcome = submitAttempt(payload, choices, gameState, config);
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
      setFeedback({ tone: "success", text: `${labels.correct} +${gameState.score}` });
      reportAfterBeat("puzzle.completed", {
        score: gameState.score,
        attempts: gameState.attempts,
      });
      return;
    }

    if (outcome.exhausted) {
      shakeToken += 1;
      setFeedback({ tone: "danger", text: `${labels.outOfAttempts} - ${payload.word}` });
      reportAfterBeat("puzzle.abandoned", { reason: "attempts-exhausted" });
      return;
    }

    // A real word, just not today's. It spent an attempt like any other miss -
    // the honesty is in the wording, not in the accounting.
    if (outcome.alternative) {
      setFeedback({
        tone: "warning",
        text: `${labels.alsoValid} - ${labels.attemptsLeft} ${attemptsLeft}`,
      });
      return;
    }

    shakeToken += 1;
    setFeedback({
      tone: "danger",
      text: `${labels.wrong} - ${labels.attemptsLeft} ${attemptsLeft}`,
    });
  }

  function fill(choiceId: string): void {
    if (gameState.finished) return;
    const next = fillNextBlank(payload, gameState, choiceId);
    if (next === gameState) return;
    gameState = next;
    setFeedback(null);
    if (isFull(payload, gameState)) submit();
  }

  function empty(blankIndex: number): void {
    gameState = clearBlank(gameState, blankIndex);
    setFeedback(null);
  }

  function undo(): void {
    gameState = undoLast(gameState);
    setFeedback(null);
  }

  function clear(): void {
    gameState = clearFilled(gameState);
    setFeedback(null);
  }

  function onChoiceKey(event: KeyboardEvent, choiceId: string): void {
    const action = keyToAction(event.key);
    if (action === null) return;
    // Handle placement here rather than letting the button synthesize a click,
    // so Enter and Space cannot place the same choice twice.
    event.preventDefault();
    if (action === "place") fill(choiceId);
    else if (action === "undo") undo();
    else clear();
    void keepFocusInPlay();
  }

  function onBlankKey(event: KeyboardEvent, blankIndex: number): void {
    const action = keyToAction(event.key);
    if (action === null) return;
    event.preventDefault();
    if (action === "clear") clear();
    else empty(blankIndex);
    void keepFocusInPlay();
  }

  /**
   * A placement removes the focused tile from the bank, which would drop focus
   * to the document body and strand a keyboard player. Move it to the next tile
   * (or, on the last one, to the word) so play continues without Tab.
   */
  async function keepFocusInPlay(): Promise<void> {
    await tick();
    const next =
      bankEl?.querySelector("button") ?? wordEl?.querySelector("button:not([disabled])");
    next?.focus();
  }

  function useHint(): void {
    const hint = pendingHint;
    if (hint === null) return;
    gameState = revealNextHint(payload, gameState);
    logger.emit("puzzle.hint.used", { data: { kind: hint.kind, cost: hint.cost } });
  }
</script>

<section
  class="mx-auto flex min-h-full w-full max-w-md flex-col justify-center gap-lg"
  data-testid="missing-letters-game"
  aria-label={labels.prompt}
>
  <header class="flex items-baseline justify-between gap-sm">
    <h2 class="font-display text-lg font-semibold text-text-primary">{labels.prompt}</h2>
    {#if !gameState.finished}
      <p class="font-mono text-text-secondary" data-testid="missing-letters-attempts">
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
      bind:this={wordEl}
      role="group"
      aria-label={labels.answer}
      data-testid="missing-letters-word"
    >
      {#each board as cell (cell.index)}
        {#if cell.blankIndex === -1}
          <!-- A printed ezhuthu: part of the clue, never a control. -->
          <div
            class="flex h-14 w-14 items-center justify-center rounded-md border border-border bg-bg-elevated font-tamil text-2xl text-text-primary shadow-sm"
            data-testid="missing-letters-shown"
            aria-label={`${labels.shown}: ${cell.ezhuthu}`}
          >
            {cell.ezhuthu}
          </div>
        {:else if cell.choiceId !== null}
          <button
            type="button"
            class="flex h-14 w-14 items-center justify-center rounded-md border border-accent bg-bg-elevated font-tamil text-2xl text-text-primary shadow-sm transition-transform duration-fast ease-spring hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
            class:border-success={gameState.solved}
            class:bg-tile-correct={gameState.solved}
            data-testid="missing-letters-blank"
            aria-label={`${labels.filledBlank} ${cell.blankIndex + 1}: ${cell.ezhuthu}`}
            disabled={gameState.finished}
            onclick={() => empty(cell.blankIndex)}
            onkeydown={(event) => onBlankKey(event, cell.blankIndex)}
          >
            {cell.ezhuthu}
          </button>
        {:else}
          <!-- An empty hole. Dashed on the page background, never a filled tile:
               `--tile-empty` is LIGHTER than `--bg-elevated` in the dark theme,
               so a filled swatch would read as the answered state. -->
          <div
            class="flex h-14 w-14 items-center justify-center rounded-md border-2 border-dashed border-text-tertiary bg-bg font-tamil text-2xl text-text-tertiary"
            data-testid="missing-letters-blank"
            aria-label={`${labels.blank} ${cell.blankIndex + 1}`}
          ></div>
        {/if}
      {/each}
    </div>
  {/key}

  <p
    class="min-h-6 text-center font-display"
    data-testid="missing-letters-feedback"
    role="status"
    aria-live="polite"
  >
    {#if feedback}
      {#key feedbackToken}
        <span
          class="inline-block"
          class:anim-pop={feedback.tone !== "warning"}
          class:anim-flip={feedback.tone === "warning"}
          class:text-success={feedback.tone === "success"}
          class:text-warning={feedback.tone === "warning"}
          class:text-danger={feedback.tone === "danger"}
        >
          {#if feedback.tone === "success"}
            <Glyph id="check" class="mr-xs inline-block align-text-bottom" />
          {/if}{feedback.text}
        </span>
      {/key}
    {/if}
  </p>

  <div
    class="flex flex-wrap justify-center gap-sm"
    bind:this={bankEl}
    role="group"
    aria-label={labels.bank}
    data-testid="missing-letters-bank"
  >
    {#each bank as choice (choice.id)}
      <button
        type="button"
        class="anim-pop flex h-14 w-14 items-center justify-center rounded-md border border-border bg-bg-elevated font-tamil text-2xl text-text-primary shadow-md transition-transform duration-fast ease-spring hover:-translate-y-1 active:translate-y-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        data-testid="missing-letters-choice"
        data-choice-id={choice.id}
        aria-label={`${labels.choice}: ${choice.ezhuthu}`}
        disabled={gameState.finished}
        onclick={() => fill(choice.id)}
        onkeydown={(event) => onChoiceKey(event, choice.id)}
      >
        {choice.ezhuthu}
      </button>
    {/each}
  </div>

  {#if (payload.hints ?? []).length > 0}
    <div class="flex flex-col items-center gap-sm">
      <!-- The price rides the BUTTON, not the revealed pill: a cost disclosed
           after the purchase is not a price, it is a receipt. -->
      <button
        type="button"
        class="inline-flex items-center gap-xs rounded-md border border-border bg-bg-elevated px-md py-sm text-text-secondary shadow-sm transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        data-testid="missing-letters-hint"
        disabled={pendingHint === null || gameState.finished}
        onclick={useHint}
      >
        <Glyph id="hint" />
        {pendingHint === null ? labels.hintsSpent : labels.hint}
        {#if pendingHint !== null}
          <span class="font-mono text-warning" data-testid="missing-letters-hint-cost">
            -{pendingHint.cost}
          </span>
        {/if}
      </button>

      {#if shownHints.length > 0}
        <!-- One rung per line: a bought meaning can be a whole phrase, and a row
             of pills would push it off a 360px screen. -->
        <ul
          class="flex w-full flex-col items-center gap-xs"
          data-testid="missing-letters-hint-list"
        >
          {#each shownHints as hint, index (index)}
            <li
              class="anim-toast-in max-w-full rounded-lg bg-bg-elevated px-md py-xs text-center font-tamil text-text-secondary shadow-sm"
            >
              {hint.text}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</section>

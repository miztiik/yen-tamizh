<script lang="ts">
  // The wordle playing surface (docs/concepts/games.md `wordle`). One verb:
  // build a row of ezhuthu and submit it, and every submitted row stays on the
  // board carrying what it taught you. The board states the rule by looking the
  // way it does - empty cells above, marked rows below - so there is nothing to
  // read before the first move (Palm #2/#10, Player #1).
  //
  // Unlike the other two Games there is no auto-submit: a row here is composed
  // one letter at a time and a player re-spells the cell they just placed all
  // the time, so submitting the moment the last cell fills would take the guess
  // away mid-thought. The submit key is therefore explicit, and a short row is
  // refused WITHOUT spending an attempt.
  //
  // This component is a thin projection of `logic.ts`: marking, composing,
  // scoring, attempts, hints and the key mapping are all pure functions there,
  // so the mechanic is unit-tested in node while this file only renders and
  // reacts.
  //
  // It reads ONLY its `payload` and the injected `GameContext` pieces (logger,
  // config slice, clock). It imports no app config, no storage, and no telemetry
  // singleton - the boundary the Oracle in `boundary.test.ts` enforces (Fowler).
  import { untrack } from "svelte";

  import Glyph from "../../designsystem/Glyph.svelte";
  import type { GameContext } from "../../session/types";

  import EzhuthuKeyboard from "./EzhuthuKeyboard.svelte";
  import MarkShape from "./MarkShape.svelte";
  import {
    applyVowelForm,
    attemptsRemaining,
    backspace,
    boardWidth,
    clearDraft,
    initialState,
    isDraftFull,
    keyStates,
    liveBase,
    markedRows,
    nextHint,
    normalizeState,
    pushEzhuthu,
    resolveLabels,
    revealNextHint,
    revealedHints,
    submitAttempt,
    type Mark,
    type WordlePayload,
    type WordleState,
  } from "./logic";

  interface Props {
    payload: WordlePayload;
    logger: GameContext["logger"];
    config: GameContext["config"];
    now: GameContext["now"];
  }

  let { payload, logger, config, now }: Props = $props();

  // A Game instance is built fresh per session item, so the payload and the
  // context never change under it. The one-time setup therefore reads them
  // untracked.
  const setup = untrack(() => {
    const celebration = config.winCelebrationMs;
    return {
      labels: resolveLabels(config),
      width: boardWidth(payload),
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
  const { labels, width, celebrationMs, startedAt } = setup;

  let gameState = $state<WordleState>(initialState());
  type Feedback = { tone: "success" | "danger"; text: string };
  let feedback = $state<Feedback | null>(null);
  // Bumped on every message so its animation re-runs even when the text repeats.
  let feedbackToken = $state(0);
  // Bumped when a SHORT row is submitted, so the shake keyframe re-runs. A
  // complete row never bumps it: every complete row is a legitimate guess, and a
  // shake there would read as "that is not a word", which this Game never says.
  let shakeToken = $state(0);

  let reported = false;
  let celebrationTimer: ReturnType<typeof setTimeout> | null = null;

  const rows = $derived(markedRows(payload, gameState));
  const states = $derived(keyStates(payload, gameState));
  const base = $derived(liveBase(gameState));
  const draftFull = $derived(isDraftFull(payload, gameState));
  const attemptsLeft = $derived(attemptsRemaining(payload, gameState));
  const shownHints = $derived(revealedHints(payload, gameState));
  const pendingHint = $derived(nextHint(payload, gameState));
  // Every row after the submitted ones and the one being composed. Rendering
  // them keeps the board a fixed height, so it never grows under the player's
  // thumb as guesses land.
  const blankRows = $derived(
    Math.max(0, payload.attempts - gameState.guesses.length - (gameState.finished ? 0 : 1)),
  );

  function setFeedback(next: Feedback | null): void {
    feedback = next;
    feedbackToken += 1;
  }

  untrack(() =>
    logger.emit("puzzle.started", {
      data: { word: payload.word, length: width, attempts: payload.attempts },
    }),
  );

  /** Serialize for the runner (GameModule.getState). */
  export function getState(): WordleState {
    return {
      ...gameState,
      guesses: gameState.guesses.map((guess) => [...guess]),
      draft: [...gameState.draft],
    };
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
        report("puzzle.completed", {
          score: gameState.score,
          attempts: gameState.guesses.length,
        }),
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

  function commit(ezhuthu: string): void {
    gameState = pushEzhuthu(payload, gameState, ezhuthu);
    setFeedback(null);
  }

  function shape(form: string): void {
    gameState = applyVowelForm(gameState, form);
    setFeedback(null);
  }

  function erase(): void {
    gameState = backspace(gameState);
    setFeedback(null);
  }

  function clear(): void {
    gameState = clearDraft(gameState);
    setFeedback(null);
  }

  function submit(): void {
    const outcome = submitAttempt(payload, gameState, config);
    if (outcome === null) {
      // A short row is not a guess yet, so it costs nothing but says so.
      shakeToken += 1;
      setFeedback({ tone: "danger", text: labels.incomplete });
      return;
    }
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
        attempts: gameState.guesses.length,
      });
      return;
    }

    if (outcome.exhausted) {
      setFeedback({ tone: "danger", text: `${labels.outOfAttempts} - ${payload.word}` });
      reportAfterBeat("puzzle.abandoned", { reason: "attempts-exhausted" });
      return;
    }

    // No message on an ordinary miss: the marks the row just earned ARE the
    // message, and a line of text repeating "wrong" would compete with them.
    setFeedback(null);
  }

  function useHint(): void {
    const hint = pendingHint;
    if (hint === null) return;
    gameState = revealNextHint(payload, gameState);
    logger.emit("puzzle.hint.used", { data: { kind: hint.kind, cost: hint.cost } });
  }

  function markLabel(mark: Mark): string {
    if (mark === "correct") return labels.markCorrect;
    if (mark === "present") return labels.markPresent;
    return labels.markAbsent;
  }
</script>

<section
  class="mx-auto flex min-h-full w-full max-w-sm flex-col gap-sm"
  data-testid="wordle-game"
  aria-label={labels.prompt}
>
  <header class="flex items-baseline justify-between gap-sm">
    <h2 class="font-display text-lg font-semibold text-text-primary">{labels.prompt}</h2>
    {#if !gameState.finished}
      <p class="font-mono text-text-secondary" data-testid="wordle-attempts">
        {labels.attemptsLeft}
        {attemptsLeft}
      </p>
    {/if}
  </header>

  <div
    class="flex flex-col items-center gap-1"
    role="group"
    aria-label={labels.board}
    data-testid="wordle-board"
    class:anim-victory={gameState.solved}
  >
    {#each rows as row, index (index)}
      <!-- A submitted row flips ONCE, as one element rather than six: a single
           composited transform is cheaper than six and reads as the row being
           turned over, which is what just happened to it. -->
      <div class="anim-flip flex gap-1" data-testid="wordle-row" data-submitted="true">
        {#each row.guess as ezhuthu, cell (cell)}
          <span
            class="relative flex h-10 w-10 items-center justify-center rounded-sm border border-border font-tamil text-xl"
            class:bg-tile-correct={row.marks[cell] === "correct"}
            class:bg-tile-present={row.marks[cell] === "present"}
            class:bg-tile-absent={row.marks[cell] === "absent"}
            class:text-tile-ink={row.marks[cell] !== "absent"}
            class:text-text-primary={row.marks[cell] === "absent"}
            data-testid="wordle-cell"
            data-mark={row.marks[cell]}
            aria-label={`${ezhuthu}: ${markLabel(row.marks[cell] ?? "absent")}`}
          >
            {ezhuthu}
            <MarkShape mark={row.marks[cell] ?? "absent"} />
          </span>
        {/each}
      </div>
    {/each}

    {#if !gameState.finished}
      {#key shakeToken}
        <div
          class="flex gap-1"
          class:anim-shake={shakeToken > 0}
          data-testid="wordle-row"
          data-draft="true"
        >
          {#each Array.from({ length: width }, (_, cell) => cell) as cell (cell)}
            {@const ezhuthu = gameState.draft[cell]}
            <span
              class="flex h-10 w-10 items-center justify-center rounded-sm border-2 bg-bg font-tamil text-xl text-text-primary"
              class:border-accent={ezhuthu !== undefined}
              class:border-dashed={ezhuthu === undefined}
              class:border-text-tertiary={ezhuthu === undefined}
              data-testid="wordle-cell"
              data-draft-cell="true"
              aria-label={ezhuthu === undefined
                ? labels.empty
                : `${labels.pending}: ${ezhuthu}`}
            >
              {ezhuthu ?? ""}
            </span>
          {/each}
        </div>
      {/key}
    {/if}

    {#each Array.from({ length: blankRows }, (_, index) => index) as index (index)}
      <div class="flex gap-1" data-testid="wordle-row" aria-hidden="true">
        {#each Array.from({ length: width }, (_, cell) => cell) as cell (cell)}
          <span
            class="h-10 w-10 rounded-sm border border-border bg-tile-empty opacity-40"
            data-testid="wordle-cell"
          ></span>
        {/each}
      </div>
    {/each}
  </div>

  <p
    class="min-h-6 text-center font-display"
    data-testid="wordle-feedback"
    role="status"
    aria-live="polite"
  >
    {#if feedback}
      {#key feedbackToken}
        <span
          class="anim-pop inline-block"
          class:text-success={feedback.tone === "success"}
          class:text-danger={feedback.tone === "danger"}
        >
          {#if feedback.tone === "success"}
            <Glyph id="check" class="mr-xs inline-block align-text-bottom" />
          {/if}{feedback.text}
        </span>
      {/key}
    {/if}
  </p>

  <EzhuthuKeyboard
    {labels}
    {states}
    {base}
    canSubmit={draftFull}
    canErase={gameState.draft.length > 0}
    disabled={gameState.finished}
    onCommit={commit}
    onForm={shape}
    onSubmit={submit}
    onErase={erase}
    onClear={clear}
  />

  {#if (payload.hints ?? []).length > 0}
    <div class="flex flex-col items-center gap-sm">
      <!-- The price rides the BUTTON, not the revealed pill: a cost disclosed
           after the purchase is not a price, it is a receipt. -->
      <button
        type="button"
        class="inline-flex items-center gap-xs rounded-md border border-border bg-bg-elevated px-md py-sm text-text-secondary shadow-sm transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        data-testid="wordle-hint"
        disabled={pendingHint === null || gameState.finished}
        onclick={useHint}
      >
        <Glyph id="hint" />
        {pendingHint === null ? labels.hintsSpent : labels.hint}
        {#if pendingHint !== null}
          <span class="font-mono text-warning" data-testid="wordle-hint-cost">
            -{pendingHint.cost}
          </span>
        {/if}
      </button>

      {#if shownHints.length > 0}
        <!-- One rung per line: a bought meaning can be a whole phrase, and a row
             of pills would push it off a 360px screen. -->
        <ul class="flex w-full flex-col items-center gap-xs" data-testid="wordle-hint-list">
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

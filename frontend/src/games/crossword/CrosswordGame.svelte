<script lang="ts">
  // The crossword playing surface (docs/concepts/games.md `crossword`). One
  // verb: write a letter into a square. The board states its own rule by looking
  // the way it does - a grid of numbered squares beside a numbered list of
  // meanings - so there is nothing to read before the first move (Palm #2/#10).
  //
  // The two input methods are ONE mechanic. Tapping a square and arrowing to it
  // both move the same caret; tapping the square you are on and pressing Enter
  // both turn the corner; a composer key and a physical keypress both go through
  // `writeEzhuthu`. A crossword that could only be played by tapping would be
  // unplayable with a keyboard, and one that needed a Tamil IME would be
  // unplayable on a phone - the composer is what makes both work (Jony).
  //
  // The composer is the Tamil letter chart, not a QWERTY: 31 keys that COMMIT a
  // whole ezhuthu on their own (12 vowels, the aytham, 18 consonants) and 13
  // that RE-SPELL the square's consonant into that row of the chart. One tap is
  // always one whole letter, so there is never a half-written cluster on the
  // board.
  //
  // It reads ONLY its `payload` and the injected `GameContext` pieces (logger,
  // config slice, clock). It imports no app config, no storage, and no telemetry
  // singleton - the boundary the Oracle in `boundary.test.ts` enforces (Fowler).
  import { tick, untrack } from "svelte";

  import Glyph from "../../designsystem/Glyph.svelte";
  import type { GameContext } from "../../session/types";

  import {
    AYTHAM,
    MEI_BASES,
    UYIR,
    VOWEL_FORMS,
    activeEntry,
    applyKey,
    applyVowelForm,
    cellKey,
    compose,
    entryCells,
    entryValue,
    initialState,
    isLockedCell,
    isSettled,
    liveBase,
    nextReveal,
    normalizeState,
    numbers,
    openCells,
    outstanding,
    resolveLabels,
    revealNext,
    setCursor,
    toggleDirection,
    writeEzhuthu,
    type Cell,
    type CrosswordPayload,
    type CrosswordState,
    type Entry,
  } from "./logic";

  interface Props {
    payload: CrosswordPayload;
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
      open: openCells(payload),
      marks: numbers(payload),
      // The win stays on screen for a moment before the runner is told and
      // clears the stage (Palm - the win moment is the reward).
      celebrationMs: typeof celebration === "number" ? celebration : 900,
      startedAt: now(),
    };
  });
  const { labels, open, marks, celebrationMs, startedAt } = setup;

  let gameState = $state<CrosswordState>(untrack(() => initialState(payload)));
  type Feedback = { tone: "success" | "muted" | "danger"; text: string };
  let feedback = $state<Feedback | null>(null);
  // Bumped on every message so its animation re-runs even when the text repeats.
  let feedbackToken = $state(0);
  let gridEl = $state<HTMLElement | undefined>();

  let reported = false;
  let attempts = 0;
  let celebrationTimer: ReturnType<typeof setTimeout> | null = null;

  const active = $derived(activeEntry(payload, gameState));
  const activeKeys = $derived(
    new Set(active === null ? [] : entryCells(active).map(cellKey)),
  );
  const left = $derived(outstanding(payload, gameState));
  const pending = $derived(nextReveal(payload, gameState));
  // The square the form row is showing the thirteen shapes OF - the caret's
  // own, or the one it just wrote and stepped past.
  const shaping = $derived(liveBase(payload, gameState));

  function setFeedback(next: Feedback | null): void {
    feedback = next;
    feedbackToken += 1;
  }

  untrack(() =>
    logger.emit("puzzle.started", {
      data: { entries: payload.entries.length, rows: payload.rows, cols: payload.cols },
    }),
  );

  /** Serialize for the runner (GameModule.getState). */
  export function getState(): CrosswordState {
    return {
      ...gameState,
      filled: { ...gameState.filled },
      revealed: [...gameState.revealed],
      cursor: { ...gameState.cursor },
    };
  }

  /** Rehydrate a persisted snapshot (GameModule.restoreState). */
  export function restoreState(raw: unknown): void {
    gameState = normalizeState(payload, raw);
    if (gameState.finished) finish();
  }

  /** Drop any pending timer (GameModule.destroy). */
  export function dispose(): void {
    if (celebrationTimer !== null) clearTimeout(celebrationTimer);
    celebrationTimer = null;
  }

  function elapsedMs(): number {
    return Math.max(0, Math.round(now() - startedAt));
  }

  function finish(): void {
    if (reported) return;
    reported = true;
    logger.emit("puzzle.completed", {
      data: {
        solved: gameState.solved,
        revealed: gameState.revealed.length,
        score: gameState.score,
        attempts,
        elapsedMs: elapsedMs(),
      },
    });
  }

  function celebrate(): void {
    if (celebrationTimer !== null) clearTimeout(celebrationTimer);
    celebrationTimer = setTimeout(finish, celebrationMs);
  }

  function onCellClick(cell: Cell): void {
    gameState = setCursor(payload, gameState, cell);
    void focusCaret();
  }

  async function focusCaret(): Promise<void> {
    await tick();
    gridEl?.querySelector<HTMLElement>('[data-cell][tabindex="0"]')?.focus();
  }

  function press(unit: string): void {
    const before = active;
    const outcome = writeEzhuthu(payload, gameState, unit, config);
    gameState = outcome.state;
    if (outcome.completed !== null) {
      attempts += 1;
      logger.emit("puzzle.attempt.submitted", {
        data: {
          number: outcome.completed.number,
          direction: outcome.completed.direction,
          correct: outcome.correct,
          attemptIndex: attempts,
          elapsedMs: elapsedMs(),
        },
      });
      setFeedback(
        outcome.correct
          ? { tone: "success", text: outcome.completed.word }
          : { tone: "danger", text: `${outcome.completed.number} ${label(outcome.completed)}` },
      );
    } else if (before !== null && feedback !== null) {
      setFeedback(null);
    }
    if (outcome.finished) celebrate();
    void focusCaret();
  }

  function form(vowel: string): void {
    // A form key is what SETTLES most Tamil answers - a word ending in a mei is
    // complete but wrong until its pulli lands - so this half of the composer
    // has to report a finished answer and a finished board just as the base
    // half does. Completeness cannot change here (the square already held a
    // letter), so what is watched is whether the answer became RIGHT.
    const before = gameState;
    const entry = active;
    gameState = applyVowelForm(payload, before, vowel);
    if (entry !== null && !isSettled(before, entry) && isSettled(gameState, entry)) {
      attempts += 1;
      logger.emit("puzzle.attempt.submitted", {
        data: {
          number: entry.number,
          direction: entry.direction,
          correct: true,
          attemptIndex: attempts,
          elapsedMs: elapsedMs(),
        },
      });
      setFeedback({ tone: "success", text: entry.word });
    }
    if (gameState.finished) celebrate();
    void focusCaret();
  }

  function erase(): void {
    gameState = applyKey(payload, gameState, "Backspace");
    void focusCaret();
  }

  function turn(): void {
    gameState = toggleDirection(payload, gameState);
    void focusCaret();
  }

  function onKeyDown(event: KeyboardEvent): void {
    const next = applyKey(payload, gameState, event.key);
    if (next === gameState && event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    gameState = next;
    void focusCaret();
  }

  function reveal(): void {
    const result = revealNext(payload, gameState, config);
    if (result.entry === null) return;
    gameState = result.state;
    logger.emit("puzzle.hint.used", { data: { kind: "reveal", cost: result.cost } });
    setFeedback({ tone: "muted", text: `${labels.revealed}: ${result.entry.word}` });
    if (gameState.finished) celebrate();
  }

  function label(entry: Entry): string {
    return entry.direction === "across" ? labels.across : labels.down;
  }
</script>

<section
  class="mx-auto flex min-h-full w-full max-w-sm flex-col gap-sm"
  data-testid="crossword-game"
  aria-label={labels.prompt}
>
  <header class="flex items-baseline justify-between gap-sm">
    <h2 class="font-display text-lg font-semibold text-text-primary">{labels.prompt}</h2>
    <p class="font-mono text-text-secondary" data-testid="crossword-remaining">
      {labels.remaining}
      {left.length}
    </p>
  </header>

  <!-- The grid is one focusable widget with a roving tabindex, not one tab stop
       per square: arrowing between squares is how a crossword is navigated, and
       36 stops would make reaching the clue list below it a chore.

       A 36px square is the CEILING, not a fixed size. Six of them with a 4px
       gutter is 236px, comfortably inside the 328px a 360px phone leaves after
       its margins; on anything narrower the tracks share what there is and the
       squares shrink together rather than the board overflowing. -->
  <div
    bind:this={gridEl}
    class="mx-auto grid w-full select-none gap-1"
    style={`grid-template-columns: repeat(${payload.cols}, minmax(0, 1fr)); max-width: calc(${payload.cols} * 2.25rem + ${payload.cols - 1} * 0.25rem);`}
    role="grid"
    tabindex={-1}
    aria-label={labels.grid}
    data-testid="crossword-grid"
    class:anim-victory={gameState.solved}
    onkeydown={onKeyDown}
  >
    {#each { length: payload.rows } as _, row (row)}
      {#each { length: payload.cols } as _, col (col)}
        {@const key = `${row},${col}`}
        {@const isOpenCell = open.has(key)}
        {@const isCaret = gameState.cursor.row === row && gameState.cursor.col === col}
        {@const inWord = activeKeys.has(key)}
        {@const locked = isOpenCell && isLockedCell(payload, gameState, { row, col })}
        {#if isOpenCell}
          <button
            type="button"
            role="gridcell"
            tabindex={isCaret ? 0 : -1}
            data-cell="true"
            data-r={row}
            data-c={col}
            data-caret={isCaret ? "true" : undefined}
            data-testid="crossword-cell"
            aria-label={`${marks.get(key) ?? ""} ${gameState.filled[key] ?? labels.grid}`.trim()}
            class="relative flex aspect-square w-full items-center justify-center rounded-sm border font-tamil text-lg transition-colors duration-fast ease-smooth focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            class:border-accent={isCaret}
            class:border-border={!isCaret}
            class:bg-tile-present={inWord && !isCaret && !locked}
            class:bg-tile-correct={isCaret}
            class:text-tile-ink={inWord || isCaret}
            class:bg-bg-elevated={!inWord && !isCaret && !locked}
            class:bg-bg-sunken={locked && !isCaret}
            class:text-text-primary={!inWord && !isCaret}
            onclick={() => onCellClick({ row, col })}
          >
            {#if marks.has(key)}
              <span class="absolute left-0.5 top-0 font-mono text-[0.5rem] leading-tight">
                {marks.get(key)}
              </span>
            {/if}
            {gameState.filled[key] ?? ""}
            {#if locked}
              <!-- The non-colour half of the cue (Jony; CLAUDE.md section 0a):
                   colour is never the only signal, so a square the player was
                   GIVEN also carries a small corner mark. -->
              <span
                aria-hidden="true"
                class="absolute bottom-0.5 right-0.5 h-1.5 w-1.5 bg-current"
              ></span>
            {/if}
          </button>
        {:else}
          <span
            aria-hidden="true"
            data-testid="crossword-block"
            class="aspect-square w-full rounded-sm bg-text-tertiary/40"
          ></span>
        {/if}
      {/each}
    {/each}
  </div>

  <p
    class="min-h-6 text-center font-display"
    data-testid="crossword-feedback"
    role="status"
    aria-live="polite"
  >
    {#if feedback}
      {#key feedbackToken}
        <span
          class="anim-pop inline-block"
          class:text-success={feedback.tone === "success"}
          class:text-danger={feedback.tone === "danger"}
          class:text-text-secondary={feedback.tone === "muted"}
        >
          {#if feedback.tone === "success"}
            <Glyph id="check" class="mr-xs inline-block align-text-bottom" />
          {/if}{feedback.text}
        </span>
      {/key}
    {/if}
  </p>

  <!-- The composer. Two rows of keys and they do different things: a BASE key
       writes a whole ezhuthu and steps along, a FORM key re-spells the square
       the caret is on into that row of the chart and stays put. The form row is
       disabled until the square holds a consonant, because there is nothing to
       re-spell before that. -->
  <div class="flex flex-col gap-xs" data-testid="crossword-keyboard" aria-label={labels.keyboard}>
    <div class="flex flex-wrap justify-center gap-1">
      {#each [...UYIR, AYTHAM, ...MEI_BASES] as base (base)}
        <button
          type="button"
          data-testid="crossword-key"
          data-key={base}
          class="min-w-8 rounded-sm border border-border bg-bg-elevated px-xs py-xs font-tamil text-base text-text-primary transition-colors duration-fast ease-smooth hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          onclick={() => press(base)}
        >
          {base}
        </button>
      {/each}
    </div>
    <div class="flex flex-wrap justify-center gap-1">
      {#each VOWEL_FORMS as vowel, index (index)}
        {@const shown = shaping === null ? null : compose(shaping, vowel)}
        <button
          type="button"
          data-testid="crossword-form"
          data-form={index}
          disabled={shaping === null}
          class="min-w-8 rounded-sm border border-border bg-bg-sunken px-xs py-xs font-tamil text-base text-text-secondary transition-colors duration-fast ease-smooth hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
          onclick={() => form(vowel)}
        >
          {shown ?? (vowel === "" ? "-" : vowel)}
        </button>
      {/each}
      <button
        type="button"
        data-testid="crossword-turn"
        class="rounded-sm border border-border bg-bg-elevated px-sm py-xs text-sm text-text-secondary transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        onclick={turn}
      >
        {labels.turn}
      </button>
      <button
        type="button"
        data-testid="crossword-erase"
        class="rounded-sm border border-border bg-bg-elevated px-sm py-xs text-sm text-text-secondary transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        onclick={erase}
      >
        {labels.erase}
      </button>
    </div>
  </div>

  <p class="text-center text-xs text-text-tertiary" data-testid="crossword-help">
    {labels.cellHint}
  </p>

  <ul class="flex w-full flex-col gap-xs" data-testid="crossword-clues" aria-label={labels.prompt}>
    {#each payload.entries as entry (entry.number + entry.direction)}
      {@const done = isSettled(gameState, entry)}
      {@const handed = gameState.revealed.includes(entry.word)}
      {@const current = active !== null && active.number === entry.number && active.direction === entry.direction}
      <li
        class="flex items-baseline gap-xs rounded-md px-md py-xs"
        class:bg-bg-elevated={!current}
        class:bg-tile-present={current}
        data-testid="crossword-clue"
        data-number={entry.number}
        data-direction={entry.direction}
        data-done={done ? "true" : "false"}
      >
        {#if done}
          <Glyph
            id={handed ? "hint" : "check"}
            class={handed ? "text-text-tertiary" : "text-success"}
          />
        {/if}
        <span class="font-mono text-xs" class:text-tile-ink={current} class:text-text-tertiary={!current}>
          {entry.number}{label(entry).slice(0, 1)}
        </span>
        <span
          class="font-tamil"
          class:text-tile-ink={current}
          class:text-text-primary={!current}
          class:line-through={done}
        >
          {entry.clue}
        </span>
      </li>
    {/each}
  </ul>

  {#if !gameState.finished}
    <div class="flex flex-col items-center gap-xs">
      <!-- The price rides the BUTTON: a cost disclosed after the purchase is
           not a price, it is a receipt. This Game bakes no hint ladder, so this
           is all the help there is, and it costs exactly the answer it hands
           over - a player stuck on the last one keeps everything else. -->
      <button
        type="button"
        class="inline-flex items-center gap-xs rounded-md border border-border bg-bg-elevated px-md py-sm text-text-secondary shadow-sm transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        data-testid="crossword-reveal"
        disabled={pending === null}
        onclick={reveal}
      >
        <Glyph id="hint" />
        {labels.reveal}
        {#if pending !== null}
          <span class="font-mono text-warning" data-testid="crossword-reveal-cost">
            -{entryValue(pending)}
          </span>
        {/if}
      </button>
    </div>
  {/if}
</section>

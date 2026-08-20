<script lang="ts">
  // The word-search playing surface (docs/concepts/games.md `word-search`). One
  // verb: draw a straight line through the grid. The board states its own rule
  // by looking the way it does - a grid of letters beside a list of words - so
  // there is nothing to read before the first move (Palm #2/#10, Player #1).
  //
  // The two input methods are ONE mechanic. A pointer press and the keyboard's
  // first Enter both drop the same anchor; dragging and the arrow keys both move
  // the same cursor; releasing and the second Enter both submit the same line.
  // Everything about what is selected and what it spells lives in `logic.ts`, so
  // a mechanic that is only playable by drag - the failure mode this Game is most
  // exposed to - is structurally impossible here (Jony, CLAUDE.md section 0a).
  //
  // Pointer moves are resolved with `elementFromPoint` rather than by listening
  // for `pointerenter` on each cell: a touch pointer is captured by the element
  // it started on and never enters another, so per-cell enter handlers work with
  // a mouse and silently do nothing on the phone this game is built for.
  //
  // It reads ONLY its `payload` and the injected `GameContext` pieces (logger,
  // config slice, clock). It imports no app config, no storage, and no telemetry
  // singleton - the boundary the Oracle in `boundary.test.ts` enforces (Fowler).
  import { tick, untrack } from "svelte";

  import Glyph from "../../designsystem/Glyph.svelte";
  import type { GameContext } from "../../session/types";

  import {
    applyKey,
    cancelTrace,
    cellAt,
    gridCols,
    gridRows,
    initialState,
    isResolved,
    markedCells,
    nextReveal,
    normalizeState,
    outstanding,
    resolveLabels,
    revealNext,
    selectedCells,
    setCursor,
    startTrace,
    submitTrace,
    wordValue,
    type Cell,
    type TraceOutcome,
    type WordSearchPayload,
    type WordSearchState,
  } from "./logic";

  interface Props {
    payload: WordSearchPayload;
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
      cols: gridCols(payload),
      // The win stays on screen for a moment before the runner is told and
      // clears the stage (Palm - the win moment is the reward).
      celebrationMs: typeof celebration === "number" ? celebration : 900,
      startedAt: now(),
    };
  });
  const { labels, cols, celebrationMs, startedAt } = setup;

  let gameState = $state<WordSearchState>(initialState());
  type Feedback = { tone: "success" | "muted" | "danger"; text: string };
  let feedback = $state<Feedback | null>(null);
  // Bumped on every message so its animation re-runs even when the text repeats.
  let feedbackToken = $state(0);
  let gridEl = $state<HTMLElement | undefined>();

  let reported = false;
  let attempts = 0;
  let celebrationTimer: ReturnType<typeof setTimeout> | null = null;

  const marked = $derived(markedCells(payload, gameState));
  const selected = $derived(selectedCells(gameState));
  const selectedKeys = $derived(new Set(selected.map((cell) => `${cell.row},${cell.col}`)));
  const left = $derived(outstanding(payload, gameState));
  const pending = $derived(nextReveal(payload, gameState));

  function setFeedback(next: Feedback | null): void {
    feedback = next;
    feedbackToken += 1;
  }

  untrack(() =>
    logger.emit("puzzle.started", {
      data: {
        targets: payload.targets.length,
        rows: gridRows(payload),
        cols: gridCols(payload),
      },
    }),
  );

  /** Serialize for the runner (GameModule.getState). */
  export function getState(): WordSearchState {
    return {
      ...gameState,
      found: gameState.found.map((trace) => ({ ...trace })),
      revealed: [...gameState.revealed],
      cursor: { ...gameState.cursor },
      anchor: gameState.anchor === null ? null : { ...gameState.anchor },
    };
  }

  /** Rehydrate a persisted snapshot (GameModule.restoreState). */
  export function restoreState(raw: unknown): void {
    gameState = normalizeState(payload, raw);
    if (!gameState.finished) return;
    // A reload after the last word landed must not strand the session: report
    // the already-decided outcome instead of replaying the beat. Deferred to a
    // microtask so the runner finishes mounting before it hears about it.
    setFeedback({ tone: "success", text: `${labels.complete} +${gameState.score}` });
    queueMicrotask(() =>
      report("puzzle.completed", {
        score: gameState.score,
        found: gameState.found.length,
        revealed: gameState.revealed.length,
      }),
    );
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

  function report(name: "puzzle.completed", data: Record<string, unknown>): void {
    if (reported) return;
    reported = true;
    logger.emit(name, { data: { ...data, elapsedMs: elapsedMs() } });
  }

  function finish(): void {
    const data = {
      score: gameState.score,
      found: gameState.found.length,
      revealed: gameState.revealed.length,
    };
    setFeedback({ tone: "success", text: `${labels.complete} +${gameState.score}` });
    if (celebrationMs <= 0) {
      report("puzzle.completed", data);
      return;
    }
    celebrationTimer = setTimeout(() => {
      celebrationTimer = null;
      report("puzzle.completed", data);
    }, celebrationMs);
  }

  function announce(outcome: TraceOutcome): void {
    if (outcome.verdict === "none") {
      setFeedback(null);
      return;
    }
    attempts += 1;
    logger.emit("puzzle.attempt.submitted", {
      data: {
        attemptIndex: attempts,
        attempt: outcome.attempt,
        correct: outcome.verdict === "found",
        elapsedMs: elapsedMs(),
      },
    });
    if (outcome.verdict === "found") {
      setFeedback({ tone: "success", text: `${labels.found} ${outcome.word}` });
    } else if (outcome.verdict === "already") {
      setFeedback({ tone: "muted", text: labels.already });
    } else if (outcome.verdict === "also-valid") {
      // A real Tamil word the grid happens to spell. Answering it is the whole
      // reason the generator records what it accidentally made.
      setFeedback({ tone: "muted", text: `${outcome.attempt} - ${labels.alsoValid}` });
    } else {
      setFeedback({ tone: "danger", text: labels.miss });
    }
    if (outcome.completed) finish();
  }

  function cellOf(target: EventTarget | null): Cell | null {
    const element = target instanceof Element ? target.closest("[data-cell]") : null;
    if (element === null) return null;
    const row = Number(element.getAttribute("data-r"));
    const col = Number(element.getAttribute("data-c"));
    return Number.isInteger(row) && Number.isInteger(col) ? { row, col } : null;
  }

  function onPointerDown(event: PointerEvent): void {
    const cell = cellOf(event.target);
    if (cell === null || gameState.finished) return;
    // Keep the gesture on this element even when the finger leaves it, and stop
    // the browser turning the drag into a scroll or a text selection.
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    gameState = startTrace(payload, gameState, cell);
    setFeedback(null);
  }

  function onPointerMove(event: PointerEvent): void {
    if (gameState.anchor === null) return;
    const under = document.elementFromPoint(event.clientX, event.clientY);
    const cell = cellOf(under);
    if (cell !== null) gameState = setCursor(payload, gameState, cell);
  }

  function onPointerUp(event: PointerEvent): void {
    if (gameState.anchor === null) return;
    const element = event.currentTarget as HTMLElement;
    if (element.hasPointerCapture(event.pointerId)) {
      element.releasePointerCapture(event.pointerId);
    }
    const outcome = submitTrace(payload, gameState, config);
    gameState = outcome.state;
    announce(outcome);
  }

  function onPointerCancel(): void {
    gameState = cancelTrace(gameState);
  }

  function onKeyDown(event: KeyboardEvent): void {
    const result = applyKey(payload, gameState, event.key, config);
    if (!result.handled) return;
    event.preventDefault();
    gameState = result.state;
    if (result.outcome !== null) announce(result.outcome);
    else if (event.key === "Escape") setFeedback(null);
    void focusCursor();
  }

  async function focusCursor(): Promise<void> {
    // The roving tabindex moves with the cursor, so the cell to focus does not
    // exist as "the tabbable one" until the DOM has caught up with the state.
    await tick();
    gridEl?.querySelector<HTMLElement>('[data-cell][tabindex="0"]')?.focus();
  }

  function reveal(): void {
    const result = revealNext(payload, gameState, config);
    if (result.word === null) return;
    gameState = result.state;
    logger.emit("puzzle.hint.used", { data: { kind: "reveal", cost: result.cost } });
    setFeedback({ tone: "muted", text: `${labels.revealed}: ${result.word}` });
    if (gameState.finished) finish();
  }
</script>

<section
  class="mx-auto flex min-h-full w-full max-w-sm flex-col gap-sm"
  data-testid="word-search-game"
  aria-label={labels.prompt}
>
  <header class="flex items-baseline justify-between gap-sm">
    <h2 class="font-display text-lg font-semibold text-text-primary">{labels.prompt}</h2>
    <p class="font-mono text-text-secondary" data-testid="word-search-remaining">
      {labels.remaining}
      {left.length}
    </p>
  </header>

  <!-- The grid is one focusable widget with a roving tabindex, not 64 tab
       stops: arrowing between cells is how a grid is navigated, and 64 stops
       would make reaching the word list below it a chore.

       A 36px cell is the CEILING, not a fixed size. Eight of them with a 4px
       gutter is 316px, which is the width this Game was designed around and
       what it takes on the 360px phone the repo targets; on anything narrower
       the tracks share what there is and the cells shrink together, because a
       grid that overflows its screen is a grid the player has to scroll to
       trace across. -->
  <div
    bind:this={gridEl}
    class="mx-auto grid w-full touch-none select-none gap-1"
    style={`grid-template-columns: repeat(${cols}, minmax(0, 1fr)); max-width: calc(${cols} * 2.25rem + ${cols - 1} * 0.25rem);`}
    role="grid"
    tabindex={-1}
    aria-label={labels.grid}
    data-testid="word-search-grid"
    class:anim-victory={gameState.solved}
    onpointerdown={onPointerDown}
    onpointermove={onPointerMove}
    onpointerup={onPointerUp}
    onpointercancel={onPointerCancel}
    onkeydown={onKeyDown}
  >
    {#each payload.grid as line, row (row)}
      {#each line as ezhuthu, col (col)}
        {@const key = `${row},${col}`}
        {@const isFound = marked.has(key)}
        {@const isPicked = selectedKeys.has(key)}
        {@const isCursor = gameState.cursor.row === row && gameState.cursor.col === col}
        <span
          role="gridcell"
          tabindex={isCursor ? 0 : -1}
          data-cell="true"
          data-r={row}
          data-c={col}
          data-found={isFound ? "true" : undefined}
          data-selected={isPicked ? "true" : undefined}
          data-testid="word-search-cell"
          aria-label={`${ezhuthu}${isFound ? ` - ${labels.found}` : ""}`}
          class="relative flex aspect-square w-full items-center justify-center rounded-sm border font-tamil text-lg transition-colors duration-fast ease-smooth focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          class:border-border={!isPicked && !isCursor}
          class:border-accent={isPicked || isCursor}
          class:bg-tile-correct={isFound}
          class:bg-tile-present={isPicked && !isFound}
          class:text-tile-ink={isFound || isPicked}
          class:bg-bg-elevated={!isPicked && !isFound}
          class:text-text-primary={!isFound && !isPicked}
        >
          {cellAt(payload, { row, col })}
          {#if isFound}
            <!-- The non-colour half of the cue (Jony; CLAUDE.md section 0a):
                 colour is never the only signal, so a settled cell also carries
                 a small filled corner square. It is not the wordle's MarkShape -
                 that component's vocabulary is correct/present/absent and it
                 lives inside another Game, which the import boundary forbids
                 reaching into. A cell here has two states, not three. -->
            <span
              aria-hidden="true"
              class="absolute right-0.5 top-0.5 h-1.5 w-1.5 bg-current"
            ></span>
          {/if}
        </span>
      {/each}
    {/each}
  </div>

  <p class="text-center text-xs text-text-tertiary" data-testid="word-search-help">
    {labels.cellHint}
  </p>

  <p
    class="min-h-6 text-center font-display"
    data-testid="word-search-feedback"
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

  <ul class="flex w-full flex-col gap-xs" data-testid="word-search-list" aria-label={labels.list}>
    {#each payload.targets as target (target.word)}
      {@const done = isResolved(gameState, target.word)}
      {@const handed = gameState.revealed.includes(target.word)}
      <li
        class="flex items-baseline gap-xs rounded-md bg-bg-elevated px-md py-xs"
        data-testid="word-search-word"
        data-word={target.word}
        data-found={done ? "true" : "false"}
      >
        <!-- Struck through AND glyphed: the line is the shape cue, the tick
             says it was traced and the hint mark says it was handed over. -->
        {#if done}
          <Glyph
            id={handed ? "hint" : "check"}
            class={handed ? "text-text-tertiary" : "text-success"}
          />
        {/if}
        <span
          class="font-tamil text-text-primary"
          class:line-through={done}
          class:text-text-tertiary={done}
        >
          {target.word}
        </span>
        {#if done && target.meaning}
          <!-- The Row 14 rule: a word that is on the board explains itself, free.
               This board is the only place these meanings can be read, because
               the session summary carries one line per item. -->
          <span class="font-tamil text-sm text-text-secondary" data-testid="word-search-meaning">
            {target.meaning}
          </span>
        {/if}
      </li>
    {/each}
  </ul>

  {#if !gameState.finished}
    <div class="flex flex-col items-center gap-xs">
      <!-- The price rides the BUTTON: a cost disclosed after the purchase is
           not a price, it is a receipt. This Game bakes no hint ladder, so this
           is all the help there is, and it costs exactly the word it hands
           over - a player stuck on the last one keeps everything else. -->
      <button
        type="button"
        class="inline-flex items-center gap-xs rounded-md border border-border bg-bg-elevated px-md py-sm text-text-secondary shadow-sm transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        data-testid="word-search-reveal"
        disabled={pending === null}
        onclick={reveal}
      >
        <Glyph id="hint" />
        {labels.reveal}
        {#if pending !== null}
          <span class="font-mono text-warning" data-testid="word-search-reveal-cost">
            -{wordValue(pending.word)}
          </span>
        {/if}
      </button>
    </div>
  {/if}
</section>

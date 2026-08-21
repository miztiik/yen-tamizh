<script lang="ts">
  // The word-ladder playing surface (docs/concepts/games.md `word-ladder`). One
  // verb: tap an ezhuthu from the bank and the rung above lights up with it
  // (Palm worldview #1). The ladder is drawn bottom rung first with the word
  // the player is standing on printed and everything above it blank, so the
  // board states the rule by looking the way it does - a row of empty steps
  // above a word you already have (Palm #2/#10, Player #1).
  //
  // The BADGE is the thing that makes the verb legible: every resolved rung
  // carries the one ezhuthu that carried it, so a climber can read their own
  // route back down the ladder and see that each step cost exactly one letter.
  //
  // This component is a thin projection of `logic.ts`: every rule (what climbs,
  // what else a pick spells, scoring, reveal, key mapping, the four completion
  // stats) is a pure function there, so the mechanic unit-tests in node while
  // this file only renders and reacts.
  //
  // It reads ONLY its `payload` and the injected `GameContext` pieces (logger,
  // config slice, clock). It imports no app config, no storage, and no
  // telemetry singleton - the boundary `boundary.test.ts` enforces (Fowler).
  import { tick, untrack } from "svelte";

  import Glyph from "../../designsystem/Glyph.svelte";
  import type { GameContext } from "../../session/types";

  import ShareCard from "./ShareCard.svelte";
  import {
    buildChoices,
    deriveStats,
    initialState,
    keyToAction,
    ladderRows,
    nextReveal,
    normalizeState,
    pickChoice,
    remainingChoices,
    resolveLabels,
    resolveStreak,
    revealNext,
    rungMarks,
    rungValue,
    stepCount,
    type LadderEvent,
    type WordLadderPayload,
    type WordLadderState,
  } from "./logic";

  interface Props {
    payload: WordLadderPayload;
    logger: GameContext["logger"];
    config: GameContext["config"];
    now: GameContext["now"];
  }

  let { payload, logger, config, now }: Props = $props();

  // A Game instance is built fresh per session item, so the payload and the
  // context never change under it. The one-time setup therefore reads them
  // untracked: the bank arrives already ordered by the bake, so neither a
  // re-render nor a resume ever reshuffles it under the player's thumb.
  const setup = untrack(() => ({
    choices: buildChoices(payload),
    labels: resolveLabels(config),
    // The run the player arrived with, read off the save by the Mode and
    // handed down as a payload. The Game never counts a streak of its own.
    streak: resolveStreak(config),
    steps: stepCount(payload),
    startedAt: now(),
  }));
  const { choices, labels, streak, steps, startedAt } = setup;

  let gameState = $state<WordLadderState>(initialState());
  // Three tones, not two: a pick that spells a REAL served word is neither a
  // climb nor a rejection, so it gets its own tone (warning + a flip that reads
  // as reappraisal) rather than being flattened into "wrong".
  type Feedback = { tone: "success" | "warning" | "danger"; text: string };
  let feedback = $state<Feedback | null>(null);
  // Bumped on every message so its animation re-runs even when the text repeats.
  let feedbackToken = $state(0);
  // Bumped on every REJECTED miss so the shake keyframe re-runs. A pick that
  // spells another word never bumps it: a shake there would read as rejection.
  let shakeToken = $state(0);
  // How many picks have been made at the rung the player is standing under.
  // It resets on every climb, which is what makes `attemptIndex === 1` mean
  // "first try at THIS rung" - the fact INSTINCT is derived from.
  let picksHere = $state(0);

  // The Game's own copy of what it emitted. The four completion stats are read
  // back off THIS, so every one of them is a function of the telemetry and the
  // save contract grows nothing (Fowler). Only what the catalog already carries
  // is recorded, so the card can state nothing the stream does not.
  const journal: LadderEvent[] = [];
  // Bumped on every journalled event so the derived stats re-read the array;
  // a plain array's push is not a signal.
  let journalled = $state(0);

  let reported = false;
  let bankEl: HTMLElement | undefined = $state();

  const rows = $derived(ladderRows(payload, choices, gameState));
  const bank = $derived(remainingChoices(choices, gameState));
  const pendingReveal = $derived(nextReveal(payload, gameState));
  const stats = $derived(journalled > 0 && gameState.finished ? deriveStats(journal) : null);
  const marks = $derived(journalled > 0 && gameState.finished ? rungMarks(journal) : []);

  function emit(name: LadderEvent["name"], data: Record<string, unknown>): void {
    journal.push({ name, data });
    journalled += 1;
  }

  function setFeedback(next: Feedback | null): void {
    feedback = next;
    feedbackToken += 1;
  }

  untrack(() => {
    const data = {
      steps,
      rungs: payload.rungs.length,
      choices: payload.choices.length,
      streak,
    };
    emit("puzzle.started", data);
    logger.emit("puzzle.started", { data });
  });

  /** Serialize for the runner (GameModule.getState). */
  export function getState(): WordLadderState {
    return {
      ...gameState,
      spentChoiceIds: [...gameState.spentChoiceIds],
      revealedSteps: [...gameState.revealedSteps],
    };
  }

  /** Rehydrate a persisted snapshot (GameModule.restoreState). */
  export function restoreState(raw: unknown): void {
    gameState = normalizeState(payload, choices, raw, config);
    replaySnapshot();
    if (!gameState.finished) return;
    // A reload with the card still unacknowledged puts the CARD back, not the
    // completion: the runner clears the stage the moment it is told, so
    // reporting here would take the result away from a player who reloaded to
    // look at it. The stats are re-derived from the replayed stream, so the
    // resumed card is built the same way the first one was.
    emit("puzzle.completed", completion());
    setFeedback({ tone: "success", text: `${labels.complete} +${gameState.score}` });
  }

  /** Nothing to release: this Game holds no timer (the card is the beat). */
  export function dispose(): void {}

  /**
   * Restate, as events, the climb a persisted snapshot proves.
   *
   * The stats are read off the stream, so a resumed play has to put the stream
   * back rather than restore a stored copy of them - which is the whole point:
   * there is no stored copy to drift (Fowler). The snapshot counts the picks
   * that MISSED but not which rung they fell under, so the replay spends one
   * miss against each climbed rung, earliest first, with any remainder against
   * the first. RETRIES therefore comes back exact and INSTINCT comes back as
   * the floor the snapshot can prove - a resumed card never claims more
   * first-try rungs than the player provably earned. Elapsed time is the one
   * thing a snapshot cannot restate, because a reload starts a new clock.
   */
  function replaySnapshot(): void {
    const resolved = gameState.spentChoiceIds.length;
    const climbedSteps: number[] = [];
    for (let step = 0; step < resolved; step += 1) {
      if (!gameState.revealedSteps.includes(step)) climbedSteps.push(step);
    }
    const spread = Math.min(gameState.misses, climbedSteps.length);
    const remainder = gameState.misses - spread;

    function replayMiss(attemptIndex: number): void {
      emit("puzzle.attempt.submitted", {
        attemptIndex,
        attempt: "",
        correct: false,
        elapsedMs: 0,
      });
    }

    // Every rung was bought, so there is no climb to hang a miss under.
    if (climbedSteps.length === 0) {
      for (let i = 0; i < gameState.misses; i += 1) replayMiss(i + 1);
    }

    let climbIndex = 0;
    for (let step = 0; step < resolved; step += 1) {
      if (gameState.revealedSteps.includes(step)) {
        emit("puzzle.hint.used", { kind: "rung", cost: rungValue() });
        continue;
      }
      const missed =
        (climbIndex < spread ? 1 : 0) + (climbIndex === 0 ? remainder : 0);
      climbIndex += 1;
      for (let i = 0; i < missed; i += 1) replayMiss(i + 1);
      emit("puzzle.attempt.submitted", {
        attemptIndex: missed + 1,
        attempt: rows[step + 1]?.added ?? "",
        correct: true,
        elapsedMs: 0,
      });
    }
  }

  function elapsedMs(): number {
    return Math.max(0, now() - startedAt);
  }

  /** What the completion event carries, wherever the climb ended. */
  function completion(): Record<string, unknown> {
    return {
      score: gameState.score,
      attempts: gameState.misses + gameState.spentChoiceIds.length,
      elapsedMs: elapsedMs(),
    };
  }

  /** Tell the runner the climb is over - once, and only through the logger. */
  function report(data: Record<string, unknown>): void {
    if (reported) return;
    reported = true;
    logger.emit("puzzle.completed", { data });
  }

  function finish(): void {
    // The completion event goes into the journal NOW, so the clock and the
    // score the card prints are the ones the runner will be told - but the
    // RUNNER is not told until the player taps through the card. That is the
    // one place this Game diverges from the other five, and it is the whole
    // reason the card exists: the runner clears the stage the instant it hears,
    // so a result on a timer is a result nobody can share (Palm, Jony).
    emit("puzzle.completed", completion());
    setFeedback({ tone: "success", text: `${labels.complete} +${gameState.score}` });
  }

  /** The player is done reading the card; hand the session back to the runner. */
  function done(): void {
    report(completion());
  }

  function pick(choiceId: string): void {
    if (gameState.finished) return;
    const outcome = pickChoice(
      payload,
      choices,
      gameState,
      choiceId,
      picksHere + 1,
      config,
    );
    if (outcome === null) return;
    gameState = outcome.state;

    const data = {
      attemptIndex: outcome.attemptIndex,
      attempt: outcome.attempt,
      correct: outcome.verdict === "climb",
      elapsedMs: elapsedMs(),
    };
    emit("puzzle.attempt.submitted", data);
    logger.emit("puzzle.attempt.submitted", { data });

    if (outcome.verdict === "climb") {
      picksHere = 0;
      setFeedback({ tone: "success", text: labels.climbed });
      if (gameState.finished) finish();
      else void keepFocusInPlay();
      return;
    }

    picksHere = outcome.attemptIndex;
    if (outcome.verdict === "also-valid") {
      // A real word, just not this rung. The honesty is in the wording: nothing
      // was spent, because a ladder charges time rather than lives.
      setFeedback({
        tone: "warning",
        text: `${labels.alsoValid} - ${outcome.spells ?? ""}`.trim(),
      });
      return;
    }
    shakeToken += 1;
    setFeedback({ tone: "danger", text: labels.miss });
  }

  function reveal(): void {
    if (pendingReveal === null) return;
    const outcome = revealNext(payload, choices, gameState, config);
    if (outcome.word === null) return;
    gameState = outcome.state;
    picksHere = 0;
    const data = { kind: "rung", cost: outcome.cost };
    emit("puzzle.hint.used", data);
    logger.emit("puzzle.hint.used", { data });
    setFeedback({ tone: "warning", text: `${labels.revealed} - ${outcome.word}` });
    if (gameState.finished) finish();
  }

  function onChoiceKey(event: KeyboardEvent, choiceId: string): void {
    if (keyToAction(event.key) === null) return;
    // Handle the pick here rather than letting the button synthesize a click,
    // so Enter and Space cannot spend the same tile twice.
    event.preventDefault();
    pick(choiceId);
    void keepFocusInPlay();
  }

  /**
   * A climb removes the spent tile from the bank, which would drop focus to the
   * document body and strand a keyboard player. Move it to the next tile so the
   * climb continues without Tab.
   */
  async function keepFocusInPlay(): Promise<void> {
    await tick();
    bankEl?.querySelector("button")?.focus();
  }
</script>

<section
  class="mx-auto flex min-h-full w-full max-w-md flex-col justify-center gap-lg"
  data-testid="word-ladder-game"
  aria-label={labels.prompt}
>
  <header class="flex items-baseline justify-between gap-sm">
    <h2 class="font-display text-lg font-semibold text-text-primary">{labels.prompt}</h2>
    <p class="font-mono text-text-secondary" data-testid="word-ladder-progress">
      {gameState.spentChoiceIds.length}/{steps}
    </p>
  </header>

  <!-- Top rung first: a ladder is climbed upward, so the target sits above the
       word the player is standing on and the given rung anchors the bottom. -->
  <ol
    class="flex flex-col-reverse gap-sm"
    class:anim-shake={shakeToken > 0 && !gameState.finished}
    class:anim-victory={gameState.solved}
    aria-label={labels.ladder}
    data-testid="word-ladder-rungs"
  >
    {#each rows as row (row.index)}
      <li
        class="flex items-center gap-sm rounded-md border px-md py-sm"
        class:anim-rung-climb={row.status === "climbed" || row.status === "revealed"}
        class:border-border={row.status === "given"}
        class:bg-bg-elevated={row.status !== "locked" && row.status !== "target"}
        class:border-success={row.status === "climbed"}
        class:border-warning={row.status === "revealed"}
        class:border-accent={row.status === "target"}
        class:border-dashed={row.status === "target" || row.status === "locked"}
        class:border-text-tertiary={row.status === "locked"}
        data-testid="word-ladder-rung"
        data-status={row.status}
        aria-label={row.word ?? labels.locked}
      >
        {#if row.added === null}
          <span class="w-12 shrink-0" aria-hidden="true"></span>
        {:else}
          <!-- The +ezhuthu badge: the one letter this rung cost. -->
          <span
            class="flex w-12 shrink-0 items-center justify-center rounded-full bg-tile-correct px-xs py-xs font-tamil text-tile-ink"
            data-testid="word-ladder-badge"
            aria-label={`+${row.added}`}
          >
            +{row.added}
          </span>
        {/if}
        <div class="flex min-w-0 flex-col">
          {#if row.word === null}
            <span class="font-tamil text-xl text-text-tertiary" aria-hidden="true">
              {"\u00B7".repeat(row.index + 1)}
            </span>
          {:else}
            <span class="font-tamil text-xl text-text-primary">{row.word}</span>
            {#if row.meaning}
              <span class="truncate font-tamil text-sm text-text-secondary">
                {row.meaning}
              </span>
            {/if}
          {/if}
        </div>
      </li>
    {/each}
  </ol>

  <p
    class="min-h-6 text-center font-display"
    data-testid="word-ladder-feedback"
    role="status"
    aria-live="polite"
  >
    {#if feedback}
      {#key feedbackToken}
        <span
          class="inline-block font-tamil"
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

  {#if gameState.finished && stats}
    <ShareCard {stats} {marks} {labels} onContinue={done} />
  {:else}
    <div
      class="flex flex-wrap justify-center gap-sm"
      bind:this={bankEl}
      role="group"
      aria-label={labels.bank}
      data-testid="word-ladder-bank"
    >
      {#each bank as choice (choice.id)}
        <button
          type="button"
          class="anim-pop flex h-14 w-14 items-center justify-center rounded-md border border-border bg-bg-elevated font-tamil text-2xl text-text-primary shadow-md transition-transform duration-fast ease-spring hover:-translate-y-1 active:translate-y-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
          data-testid="word-ladder-choice"
          data-choice-id={choice.id}
          aria-label={`${labels.choice}: ${choice.ezhuthu}`}
          onclick={() => pick(choice.id)}
          onkeydown={(event) => onChoiceKey(event, choice.id)}
        >
          {choice.ezhuthu}
        </button>
      {/each}
    </div>

    <div class="flex justify-center">
      <!-- The price rides the BUTTON, not the revealed rung: a cost disclosed
           after the purchase is not a price, it is a receipt. -->
      <button
        type="button"
        class="inline-flex items-center gap-xs rounded-md border border-border bg-bg-elevated px-md py-sm text-text-secondary shadow-sm transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        data-testid="word-ladder-reveal"
        disabled={pendingReveal === null}
        onclick={reveal}
      >
        <Glyph id="hint" />
        {labels.reveal}
      </button>
    </div>
  {/if}
</section>

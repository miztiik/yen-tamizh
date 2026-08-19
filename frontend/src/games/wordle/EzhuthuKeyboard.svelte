<script lang="ts">
  // The ezhuthu composer - this Game's answer to "247 keys do not fit on a
  // phone" (docs/concepts/games.md `wordle`).
  //
  // Tamil writes a syllable as one letter: 12 uyir, 18 mei, 216 uyirmei and the
  // aytham. A flat keyboard of all 247 is not a layout problem to be solved with
  // scrolling, it is the wrong model - a Tamil reader does not hold 247 symbols,
  // they hold 30 letters and 13 shapes, which is exactly how the letter chart
  // they learned to read from is drawn. So this keyboard is that chart:
  //
  //   - THIRTY-ONE COMMITTING KEYS. Twelve uyir, the aytham, and each consonant
  //     in its bare form. One tap places one whole ezhuthu, so the commonest
  //     case - a bare uyirmei, which is what a Tamil consonant key already
  //     is - costs a single tap and nothing is ever left half-composed.
  //   - THIRTEEN FORM KEYS that RE-SPELL the cell just placed, showing that
  //     letter's own chart row live: mei first, then the twelve uyirmei. Tapping
  //     `ka` then `aa` gives `kaa`; tapping `i` next gives `ki`, because a vowel
  //     sign replaces the shape rather than adding a letter. There is no pending
  //     state and no commit key, so a player can never be stranded mid-letter.
  //   - KEY STATE IS EXACT, NEVER AGGREGATED. Every key is coloured by the state
  //     of the ezhuthu it would commit RIGHT NOW - which for a form key changes
  //     as the live base changes, turning this row into a per-letter readout
  //     that a flat 26-key English keyboard cannot offer. Rolling the 12 forms
  //     of a base up into one verdict was the alternative and it has no honest
  //     answer: `kaa` being absent says nothing about `ku`, and greying the base
  //     on that evidence would hide a letter the answer may still hold.
  //
  // Every key is a real button, so Tab reaches all of them and Enter or Space
  // presses them; Backspace and Escape work from any key.
  import Glyph from "../../designsystem/Glyph.svelte";

  import MarkShape from "./MarkShape.svelte";
  import {
    AYTHAM,
    MEI_BASES,
    PULLI,
    UYIR,
    VOWEL_FORMS,
    compose,
    keyToAction,
    type Mark,
    type WordleLabels,
  } from "./logic";

  interface Props {
    labels: WordleLabels;
    /** The best mark known for each ezhuthu so far. */
    states: Map<string, Mark>;
    /** The base whose chart row the form keys are showing, or null for none. */
    base: string | null;
    /**
     * Whether the row is complete. It styles the submit key rather than
     * disabling it: a dead key teaches nothing, so a short row is submitted,
     * refused with a reason, and costs no attempt.
     */
    canSubmit: boolean;
    canErase: boolean;
    disabled: boolean;
    onCommit: (ezhuthu: string) => void;
    onForm: (form: string) => void;
    onSubmit: () => void;
    onErase: () => void;
    onClear: () => void;
  }

  let {
    labels,
    states,
    base,
    canSubmit,
    canErase,
    disabled,
    onCommit,
    onForm,
    onSubmit,
    onErase,
    onClear,
  }: Props = $props();

  // U+25CC DOTTED CIRCLE - the standard carrier for a combining mark shown on
  // its own, so a form key still reads as a letter shape when no base is live.
  // Those keys are disabled in that state; the placeholder is what stops the row
  // from rendering eleven floating accents.
  const PLACEHOLDER = "\u25CC";

  const VOWEL_KEYS = [...UYIR, AYTHAM];

  function formLabel(form: string): string {
    return compose(base ?? PLACEHOLDER, form);
  }

  /** The ezhuthu a form key would commit, or null when no base is live. */
  function formTarget(form: string): string | null {
    return base === null ? null : compose(base, form);
  }

  function onKey(event: KeyboardEvent, press: () => void): void {
    const action = keyToAction(event.key);
    if (action === null) return;
    // Handled here rather than letting the button synthesize a click, so Enter
    // and Space cannot fire the same key twice.
    event.preventDefault();
    if (action === "press") press();
    else if (action === "undo") onErase();
    else onClear();
  }
</script>

<!--
  The form row sits directly under the board on purpose: it is the one row whose
  CONTENT changes, and putting it next to the cell it re-spells is what makes
  "these are the shapes of the letter I just placed" legible without a caption.
-->
<div class="flex flex-col gap-sm" data-testid="wordle-keyboard">
  <div
    class="grid grid-cols-7 gap-1"
    role="group"
    aria-label={labels.forms}
    data-testid="wordle-forms"
  >
    {#each VOWEL_FORMS as form (form)}
      {@const target = formTarget(form)}
      {@const mark = target === null ? undefined : states.get(target)}
      <button
        type="button"
        class="relative flex h-10 items-center justify-center rounded-sm border border-border bg-bg-elevated font-tamil text-lg text-text-primary transition-transform duration-fast ease-spring hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        class:bg-tile-correct={mark === "correct"}
        class:bg-tile-present={mark === "present"}
        class:bg-tile-absent={mark === "absent"}
        class:text-tile-ink={mark === "correct" || mark === "present"}
        data-testid="wordle-form-key"
        data-form={form === "" ? "inherent" : form === PULLI ? "pulli" : form}
        aria-label={target ?? formLabel(form)}
        aria-disabled={base === null}
        disabled={disabled || base === null}
        onclick={() => onForm(form)}
        onkeydown={(event) => onKey(event, () => onForm(form))}
      >
        {formLabel(form)}
        {#if mark !== undefined}
          <MarkShape {mark} />
        {/if}
      </button>
    {/each}
  </div>

  <div
    class="grid grid-cols-7 gap-1"
    role="group"
    aria-label={labels.vowels}
    data-testid="wordle-vowels"
  >
    {#each VOWEL_KEYS as ezhuthu (ezhuthu)}
      {@const mark = states.get(ezhuthu)}
      <button
        type="button"
        class="relative flex h-10 items-center justify-center rounded-sm border border-border bg-bg-elevated font-tamil text-lg text-text-primary transition-transform duration-fast ease-spring hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        class:bg-tile-correct={mark === "correct"}
        class:bg-tile-present={mark === "present"}
        class:bg-tile-absent={mark === "absent"}
        class:text-tile-ink={mark === "correct" || mark === "present"}
        data-testid="wordle-key"
        data-ezhuthu={ezhuthu}
        aria-label={ezhuthu}
        {disabled}
        onclick={() => onCommit(ezhuthu)}
        onkeydown={(event) => onKey(event, () => onCommit(ezhuthu))}
      >
        {ezhuthu}
        {#if mark !== undefined}
          <MarkShape {mark} />
        {/if}
      </button>
    {/each}
  </div>

  <div
    class="grid grid-cols-6 gap-1"
    role="group"
    aria-label={labels.consonants}
    data-testid="wordle-consonants"
  >
    {#each MEI_BASES as consonant (consonant)}
      {@const mark = states.get(consonant)}
      <button
        type="button"
        class="relative flex h-10 items-center justify-center rounded-sm border border-border bg-bg-elevated font-tamil text-lg text-text-primary transition-transform duration-fast ease-spring hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
        class:bg-tile-correct={mark === "correct"}
        class:bg-tile-present={mark === "present"}
        class:bg-tile-absent={mark === "absent"}
        class:text-tile-ink={mark === "correct" || mark === "present"}
        class:ring-2={base === consonant}
        class:ring-accent={base === consonant}
        data-testid="wordle-key"
        data-ezhuthu={consonant}
        aria-label={consonant}
        {disabled}
        onclick={() => onCommit(consonant)}
        onkeydown={(event) => onKey(event, () => onCommit(consonant))}
      >
        {consonant}
        {#if mark !== undefined}
          <MarkShape {mark} />
        {/if}
      </button>
    {/each}
  </div>

  <div class="grid grid-cols-2 gap-1">
    <button
      type="button"
      class="flex h-10 items-center justify-center gap-xs rounded-sm border border-border bg-bg-elevated text-text-secondary transition-transform duration-fast ease-spring hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
      data-testid="wordle-erase"
      aria-label={labels.erase}
      disabled={disabled || !canErase}
      onclick={onErase}
      onkeydown={(event) => onKey(event, onErase)}
    >
      <Glyph id="back" />
    </button>
    <button
      type="button"
      class="flex h-10 items-center justify-center gap-xs rounded-sm border bg-bg-elevated font-display text-text-primary transition-transform duration-fast ease-spring hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
      class:border-accent={canSubmit}
      class:border-border={!canSubmit}
      class:text-text-tertiary={!canSubmit}
      data-testid="wordle-submit"
      data-ready={canSubmit ? "true" : "false"}
      aria-label={labels.submit}
      {disabled}
      onclick={onSubmit}
      onkeydown={(event) => onKey(event, onSubmit)}
    >
      <Glyph id="check" />
    </button>
  </div>
</div>

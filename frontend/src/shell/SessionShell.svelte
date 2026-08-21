<script lang="ts">
  // SessionShell - the ONE responsive chrome that hosts every session (docs/
  // concepts/ui-shell.md). Four landmark slots: header / rail / stage / footer.
  // A Game renders into `stage` ONLY; the shell owns everything else, once, so
  // responsive behaviour (the rail becoming a bottom sheet on a phone) is never
  // duplicated per Game (Jony + Fowler, the DRY-UI invariant).
  //
  // Chrome is built from Row 10 tokens + glyphs (no bespoke colours, no inline
  // SVG). Every control is a real <button> in a semantic landmark, keyboard
  // reachable, with a visible focus ring (v2 a11y: labelled controls, semantic
  // landmarks, focus-visible outlines).
  import type { Snippet } from "svelte";
  import { untrack } from "svelte";

  import Glyph from "../designsystem/Glyph.svelte";
  import type { Logger } from "../telemetry/logger";
  import { setLoggerContext } from "./context";

  interface Progress {
    completed: number;
    total: number;
  }

  interface Props {
    /** Injected into context for descendant chrome (never a singleton). */
    logger: Logger;
    title?: string;
    backLabel?: string;
    settingsLabel?: string;
    /** Item progress; the shell draws the dot indicator in the rail. */
    progress?: Progress | null;
    /**
     * Header content between the title and the settings control - the slot for
     * a status readout that must never scroll away (the Time Trial's clock).
     * It sits in the header rather than the rail because the rail becomes a
     * bottom sheet on a phone, and a countdown a player has to look down for is
     * a countdown they stop reading.
     */
    headerAside?: Snippet;
    /** Secondary rail content (above the progress dots). */
    rail?: Snippet;
    /** Footer toolbar content (hint / check / shuffle land here in later rows). */
    footer?: Snippet;
    /** Bound out to the parent: the element Games mount into. */
    stage?: HTMLElement;
    onExit?: () => void;
    onSettings?: () => void;
  }

  let {
    logger,
    title = "yen-tamizh",
    backLabel = "Back to home",
    settingsLabel = "Settings",
    progress = null,
    headerAside,
    rail,
    footer,
    stage = $bindable(),
    onExit,
    onSettings,
  }: Props = $props();

  // The logger is stable for a shell instance; capture the current value once
  // (untrack signals the intent, so it is not a reactive-read smell).
  setLoggerContext(untrack(() => logger));

  let stageEl: HTMLElement | undefined = $state();
  // Expose the stage element to the parent once it exists, so the SessionRunner
  // can mount Games into it (the Game's only surface).
  $effect(() => {
    stage = stageEl;
  });
</script>

<div class="flex min-h-dvh flex-col bg-bg text-text-primary">
  <header
    class="flex shrink-0 items-center justify-between gap-sm border-b border-border bg-bg-elevated px-lg py-md shadow-sm"
  >
    <button
      type="button"
      class="inline-flex items-center gap-xs rounded-md px-sm py-xs text-text-secondary transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      aria-label={backLabel}
      onclick={() => onExit?.()}
    >
      <Glyph id="back" title={backLabel} />
      <span class="hidden sm:inline">{backLabel}</span>
    </button>

    <h1 class="truncate font-display text-lg font-semibold text-text-primary">{title}</h1>

    <div class="flex shrink-0 items-center gap-xs">
      {#if headerAside}{@render headerAside()}{/if}
      <button
        type="button"
        class="inline-flex items-center rounded-md p-xs text-text-secondary transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        aria-label={settingsLabel}
        onclick={() => onSettings?.()}
      >
        <Glyph id="settings" title={settingsLabel} />
      </button>
    </div>
  </header>

  <div class="flex min-h-0 flex-1 flex-col md:flex-row">
    <aside
      class="order-last flex shrink-0 items-center justify-center gap-md border-t border-border bg-bg-elevated px-lg py-md md:order-none md:w-56 md:flex-col md:items-stretch md:border-r md:border-t-0"
      aria-label="Session status"
    >
      {#if rail}{@render rail()}{/if}
      {#if progress}
        <div
          class="flex items-center gap-xs"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={progress.total}
          aria-valuenow={progress.completed}
          aria-label={`${progress.completed} of ${progress.total} complete`}
        >
          {#each Array.from({ length: progress.total }, (_, i) => i) as i (i)}
            {@const done = i < progress.completed}
            {@const current = i === progress.completed}
            <span
              class="inline-block rounded-full transition-all duration-base ease-smooth"
              class:bg-success={done}
              class:bg-accent={current}
              class:bg-border={!done && !current}
              style={done || current ? "width:0.6rem;height:0.6rem" : "width:0.4rem;height:0.4rem"}
            ></span>
          {/each}
          <span class="ml-xs font-mono text-text-tertiary">
            {Math.min(progress.completed + 1, progress.total)}/{progress.total}
          </span>
        </div>
      {/if}
    </aside>

    <main bind:this={stageEl} class="min-w-0 flex-1 p-lg" data-testid="session-stage"></main>
  </div>

  <footer
    class="shrink-0 border-t border-border bg-bg-elevated px-lg py-md"
    data-testid="session-footer"
  >
    {#if footer}{@render footer()}{/if}
  </footer>
</div>

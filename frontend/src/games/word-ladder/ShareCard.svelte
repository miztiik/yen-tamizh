<script lang="ts">
  // The result card (docs/concepts/journeys.md - the completion moment). It is
  // rendered HERE, on the player's device, out of DOM the bundle already ships:
  // no endpoint, no server-rendered image, no share id. A static game has
  // nothing to call, and a brag that needs a server is a brag that stops
  // working the day the server does (Holy Law #1). `boundary.test.ts` asserts
  // structurally that no network API appears anywhere in this Game, and the
  // e2e asserts no request leaves the page while the card is on screen.
  //
  // It is purely presentational: the four stats arrive as a prop, already
  // derived from the emitted event stream by `deriveStats`, so the card cannot
  // claim anything the telemetry did not record.
  import Glyph from "../../designsystem/Glyph.svelte";

  import {
    formatDuration,
    markGlyph,
    shareText,
    type LadderStats,
    type RungMark,
    type WordLadderLabels,
  } from "./logic";

  interface Props {
    stats: LadderStats;
    marks: RungMark[];
    labels: WordLadderLabels;
    /** Hand the session back to the runner; the card is the gate on advancing. */
    onContinue: () => void;
  }

  let { stats, marks, labels, onContinue }: Props = $props();

  let copied = $state(false);

  const text = $derived(shareText(stats, marks, labels));
  const rows = $derived([
    { key: "time", label: labels.statTime, value: formatDuration(stats.timeMs) },
    {
      key: "instinct",
      label: labels.statInstinct,
      value: `${stats.instinct}/${stats.steps}`,
    },
    { key: "retries", label: labels.statRetries, value: `${stats.retries}` },
    { key: "streak", label: labels.statStreak, value: `${stats.streak}` },
  ]);

  async function copy(): Promise<void> {
    // Clipboard only - a local move, and the one the card's own DOM already
    // backs up: the marks and the stat grid are real selectable text, so a
    // browser that refuses the clipboard costs the player a tap, not the brag.
    const clipboard = navigator.clipboard;
    if (clipboard === undefined) return;
    try {
      await clipboard.writeText(text);
      copied = true;
    } catch {
      copied = false;
    }
  }
</script>

<section
  class="anim-pop flex w-full flex-col items-center gap-md rounded-lg border border-border bg-bg-elevated p-md shadow-lg"
  data-testid="word-ladder-card"
  aria-label={labels.card}
>
  <h3 class="font-display text-lg font-semibold text-success">{labels.complete}</h3>

  <p
    class="font-mono text-xl tracking-widest text-accent"
    data-testid="word-ladder-card-marks"
  >
    {#each marks as mark, index (index)}<span>{markGlyph(mark)}</span>{/each}
  </p>

  <dl class="grid w-full grid-cols-2 gap-sm" data-testid="word-ladder-card-stats">
    {#each rows as row (row.key)}
      <div class="flex flex-col items-center gap-xs rounded-md bg-bg p-sm">
        <dt class="font-tamil text-sm text-text-secondary">{row.label}</dt>
        <dd
          class="font-mono text-xl text-text-primary"
          data-testid={`word-ladder-stat-${row.key}`}
        >
          {row.value}
        </dd>
      </div>
    {/each}
  </dl>

  <div class="flex flex-wrap justify-center gap-sm">
    <button
      type="button"
      class="inline-flex items-center gap-xs rounded-md border border-border px-md py-sm text-text-secondary transition-colors duration-fast ease-smooth hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      data-testid="word-ladder-share"
      onclick={copy}
    >
      <Glyph id="share" />
      {copied ? labels.shared : labels.share}
    </button>

    <button
      type="button"
      class="inline-flex items-center gap-xs rounded-md bg-accent px-md py-sm font-semibold text-tile-ink shadow-md transition-transform duration-fast ease-spring hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      data-testid="word-ladder-continue"
      onclick={onContinue}
    >
      {labels.continueOn}
      <Glyph id="check" />
    </button>
  </div>
</section>

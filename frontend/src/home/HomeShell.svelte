<script lang="ts">
  // The Home - the first screen, and the whole navigation model (docs/concepts/
  // ui-shell.md). One tap from here to playing: the enabled Mode card IS the
  // start button, so a player who cannot read the interface still gets in
  // (Player #1: I came here to play, not to read).
  //
  // Modes that are not built yet are shown as static cards with a "coming soon"
  // pill rather than disabled buttons - a dead control invites a tap and then
  // punishes it, while a card that is plainly not a button never lies (Jony:
  // remove before adding). Which Modes are live comes from config, never from a
  // hardcoded list here.
  import Glyph from "../designsystem/Glyph.svelte";
  import { APP_TITLE } from "../lib/meta";
  import { copyText, isModeEnabled } from "../lib/config";
  import { MODE_CARDS } from "./modes";

  interface Props {
    /** The player's current run, drawn only when there is one to brag about. */
    streak?: number;
    onPlay: (modeId: string) => void;
  }

  let { streak = 0, onPlay }: Props = $props();

  const cards = MODE_CARDS.map((card) => ({
    ...card,
    enabled: isModeEnabled(card.modeId),
    title: copyText(card.titleSlug),
    titleEn: copyText(card.titleEnSlug),
    note: copyText(card.noteSlug),
  }));
</script>

<main
  class="mx-auto flex min-h-dvh w-full max-w-md flex-col gap-lg p-lg"
  data-testid="app-shell"
>
  <header class="flex flex-col items-center gap-xs pt-xl text-center">
    <h1 class="font-display text-3xl font-extrabold tracking-tight text-accent">
      {APP_TITLE}
    </h1>
    <p class="font-tamil text-text-secondary">{copyText("home-tagline")}</p>
    {#if streak > 0}
      <p
        class="mt-xs inline-flex items-center gap-xs rounded-full bg-bg-elevated px-md py-xs text-sm text-text-secondary"
        data-testid="home-streak"
      >
        <Glyph id="star" class="text-warning" />
        <span class="font-tamil">{copyText("summary-streak")}</span>
        <span class="font-mono text-text-primary">{streak}</span>
      </p>
    {/if}
  </header>

  <ul
    class="flex flex-col gap-md"
    aria-label={copyText("home-modes-label")}
    data-testid="home-modes"
  >
    {#each cards as card (card.modeId)}
      <li>
        {#if card.enabled}
          <button
            type="button"
            class="flex w-full items-center gap-md rounded-lg border border-border bg-bg-elevated p-lg text-left shadow-sm transition-transform duration-fast ease-spring hover:-translate-y-px hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:translate-y-0"
            data-testid="mode-card"
            data-mode={card.modeId}
            aria-label={`${card.title} - ${copyText("action-play")}`}
            onclick={() => onPlay(card.modeId)}
          >
            <Glyph id={card.glyphId} size="1.75rem" class="shrink-0 text-accent" />
            <span class="flex min-w-0 flex-col">
              <span class="font-tamil text-lg font-semibold text-text-primary">
                {card.title}
              </span>
              <span class="truncate font-tamil text-sm text-text-secondary">{card.note}</span>
              <span class="text-xs uppercase tracking-wide text-text-tertiary">
                {card.titleEn}
              </span>
            </span>
          </button>
        {:else}
          <div
            class="flex w-full items-center gap-md rounded-lg border border-dashed border-border p-lg opacity-70"
            data-testid="mode-card-locked"
            data-mode={card.modeId}
          >
            <Glyph id={card.glyphId} size="1.75rem" class="shrink-0 text-text-tertiary" />
            <span class="flex min-w-0 flex-col">
              <span class="font-tamil text-lg font-semibold text-text-secondary">
                {card.title}
              </span>
              <span class="truncate font-tamil text-sm text-text-tertiary">{card.note}</span>
            </span>
            <span
              class="ml-auto shrink-0 rounded-full bg-bg-elevated px-sm py-xs font-tamil text-xs text-text-tertiary"
            >
              {copyText("mode-coming-soon")}
            </span>
          </div>
        {/if}
      </li>
    {/each}
  </ul>
</main>

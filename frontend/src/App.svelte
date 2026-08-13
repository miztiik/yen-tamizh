<script lang="ts">
  import { onMount, type Component } from "svelte";

  import { APP_TITLE, APP_TAGLINE } from "./lib/meta";

  // The default view is the skeleton title screen (Row 3). Row 11 added a
  // developer harness behind `?harness=session` (the fake-Game runtime proof)
  // and Row 12 adds `?harness=anagram` (the first playable Game inside that same
  // runtime). Both are lazy-imported so they never weigh on the default critical
  // path (Carmack). Row 13 replaces them with the real Home.
  let Harness = $state<Component | null>(null);

  onMount(async () => {
    const harness = new URLSearchParams(window.location.search).get("harness");
    if (harness === "session") {
      Harness = (await import("./shell/SessionHarness.svelte")).default;
    } else if (harness === "anagram") {
      Harness = (await import("./shell/AnagramHarness.svelte")).default;
    }
  });
</script>

{#if Harness}
  <Harness />
{:else}
  <main
    class="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center"
    data-testid="app-shell"
  >
    <h1 class="shell-title">{APP_TITLE}</h1>
    <p class="shell-tagline">{APP_TAGLINE}</p>
  </main>
{/if}

<style>
  .shell-title {
    margin: 0;
    font-size: clamp(2rem, 8vw, 3.5rem);
    font-weight: 800;
    letter-spacing: -0.02em;
    color: var(--accent);
  }

  .shell-tagline {
    margin: 0;
    max-width: 28ch;
    color: var(--text-secondary);
    font-size: 1rem;
  }
</style>

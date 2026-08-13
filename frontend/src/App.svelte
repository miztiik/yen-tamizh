<script lang="ts">
  import { onMount, type Component } from "svelte";

  import { APP_TITLE, APP_TAGLINE } from "./lib/meta";

  // The default view is the skeleton title screen (Row 3). Row 11 adds a
  // developer harness behind `?harness=session` that boots the SessionShell +
  // SessionRunner over a fake session; it is lazy-imported so it never weighs on
  // the default critical path (Carmack). Row 13 replaces this with the real Home.
  let Harness = $state<Component | null>(null);

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("harness") === "session") {
      Harness = (await import("./shell/SessionHarness.svelte")).default;
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

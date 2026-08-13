<script lang="ts">
  import { APP_TITLE, APP_TAGLINE } from "./lib/meta";
</script>

<main class="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center" data-testid="app-shell">
  <h1 class="shell-title">{APP_TITLE}</h1>
  <p class="shell-tagline">{APP_TAGLINE}</p>
</main>

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

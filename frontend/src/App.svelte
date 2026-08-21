<script lang="ts">
  import { onMount, type Component } from "svelte";

  import HomeShell from "./home/HomeShell.svelte";
  import { StorageService } from "./services/StorageService";

  // Routing is two screens and a query string, not a router: the Home, and the
  // Mode a player tapped (`?mode=daily`). pushState keeps the browser Back
  // button honest and makes the session deep-linkable, which costs 20 lines
  // instead of a dependency (Holy Law #8).
  //
  // The Row 11/12 developer harnesses stay reachable behind `?harness=` - they
  // are the isolated proofs of the runtime and of the Game, and the daily path
  // exercises neither in isolation. Both they and the session screen are lazy
  // imports, so the Home's critical path carries neither (Carmack).
  let Harness = $state<Component | null>(null);
  let DailySession = $state<Component<{ onHome: () => void }> | null>(null);
  let view = $state<"home" | "daily">("home");
  let streak = $state(0);

  async function openDaily(): Promise<void> {
    if (DailySession === null) {
      DailySession = (await import("./shell/DailySession.svelte")).default;
    }
    view = "daily";
  }

  function readStreak(): void {
    // A corrupt or absent save reads as no streak, never as a crash.
    streak = new StorageService({ store: localStorage }).loadSave()?.streak ?? 0;
  }

  function goHome(): void {
    view = "home";
    readStreak();
    if (window.location.search) {
      window.history.pushState({}, "", window.location.pathname);
    }
  }

  function play(modeId: string): void {
    if (modeId !== "daily") return;
    window.history.pushState({}, "", "?mode=daily");
    void openDaily();
  }

  async function applyLocation(): Promise<void> {
    const params = new URLSearchParams(window.location.search);
    const harness = params.get("harness");
    if (harness === "session") {
      Harness = (await import("./shell/SessionHarness.svelte")).default;
      return;
    }
    if (harness === "anagram") {
      Harness = (await import("./shell/AnagramHarness.svelte")).default;
      return;
    }
    if (harness === "missing-letters") {
      Harness = (await import("./shell/MissingLettersHarness.svelte")).default;
      return;
    }
    if (harness === "wordle") {
      Harness = (await import("./shell/WordleHarness.svelte")).default;
      return;
    }
    if (harness === "word-search") {
      Harness = (await import("./shell/WordSearchHarness.svelte")).default;
      return;
    }
    if (harness === "crossword") {
      Harness = (await import("./shell/CrosswordHarness.svelte")).default;
      return;
    }
    if (harness === "word-ladder") {
      Harness = (await import("./shell/WordLadderHarness.svelte")).default;
      return;
    }
    Harness = null;
    if (params.get("mode") === "daily") {
      await openDaily();
      return;
    }
    view = "home";
  }

  onMount(() => {
    readStreak();
    void applyLocation();
    const onPop = (): void => void applyLocation();
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  });
</script>

{#if Harness}
  <Harness />
{:else if view === "daily" && DailySession}
  <DailySession onHome={goHome} />
{:else}
  <HomeShell {streak} onPlay={play} />
{/if}

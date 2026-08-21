<script lang="ts">
  // The Journey screen - the map, and the node the player tapped.
  //
  // It wires the real runtime (Row 11) to the authored path (Row 17):
  // JourneyMode reads the file and answers which nodes are reachable, the map
  // draws them, and the SessionRunner walks the one node at a time. This
  // component owns only the framing a Mode cannot: loading, unavailable, and
  // the return to the map.
  //
  // Progress is recorded HERE, once, when a node's session completes - never
  // inside the Game (which must never see storage) and never per attempt.
  // StorageService is the single writer, and the record it keeps is the Mode's
  // day-independent one: a path is not a calendar.
  import SessionShell from "./SessionShell.svelte";
  import JourneyMap from "../home/JourneyMap.svelte";
  import Glyph from "../designsystem/Glyph.svelte";
  import { createRuntime } from "../telemetry/runtime";
  import { StorageService } from "../services/StorageService";
  import { SessionRunner, type SessionHost } from "../session/SessionRunner";
  import { GAME_REGISTRY } from "../games/registry";
  import { APP_CONFIG, copyText } from "../lib/config";
  import { todayIso } from "../lib/dates";
  import type { Journey } from "../contracts";
  import {
    JOURNEY_MODE_ID,
    completedNodeIds,
    loadJourney,
    nodeStates,
    toSession,
    withNodeCompleted,
  } from "../modes/JourneyMode";

  interface Props {
    onHome: () => void;
  }

  let { onHome }: Props = $props();

  const runtime = createRuntime({ dev: import.meta.env.DEV });
  const storage = new StorageService({ store: localStorage });
  const journeyId = APP_CONFIG.ui.defaultJourney;

  type Phase = "loading" | "map" | "playing" | "unavailable";

  let phase = $state<Phase>("loading");
  let journey = $state<Journey | null>(null);
  let completed = $state<string[]>([]);
  let activeNodeId = $state<string | null>(null);
  let progress = $state<{ completed: number; total: number } | null>(null);
  let stageEl = $state<HTMLElement | undefined>();
  let runner: SessionRunner | null = null;

  const states = $derived(journey === null ? [] : nodeStates(journey, completed));
  const activeNode = $derived(
    journey === null || activeNodeId === null
      ? null
      : (journey.nodes.find((node) => node.id === activeNodeId) ?? null),
  );

  function readProgress(): void {
    completed = completedNodeIds(storage.readModeProgress(JOURNEY_MODE_ID), journeyId);
  }

  void (async () => {
    const loaded = await loadJourney({ journeyId });
    if (loaded.status === "ready") {
      journey = loaded.journey;
      readProgress();
      phase = "map";
    } else {
      phase = "unavailable";
    }
  })();

  function play(nodeId: string): void {
    activeNodeId = nodeId;
    phase = "playing";
  }

  function stop(): void {
    runner?.exit();
    runner = null;
    activeNodeId = null;
    progress = null;
    phase = "map";
  }

  /** One node cleared: record it, then hand the player back to the path. */
  function finish(): void {
    const current = journey;
    const node = activeNode;
    if (current === null || node === null) return;
    storage.writeModeProgress(
      {
        date: todayIso(),
        modeId: JOURNEY_MODE_ID,
        gameId: node.gameId,
        packId: node.packId,
      },
      withNodeCompleted(storage.readModeProgress(JOURNEY_MODE_ID), current.id, node.id),
    );
    readProgress();
    runner = null;
    activeNodeId = null;
    progress = null;
    phase = "map";
  }

  // The runner mounts a Game into the shell's stage, so it can only start once
  // the shell has bound that element - and only once per NODE, which is what
  // makes leaving a node and opening the next one a fresh session rather than a
  // resumed one.
  $effect(() => {
    const stage = stageEl;
    const current = journey;
    const node = activeNode;
    if (stage === undefined || current === null || node === null || runner !== null) {
      return;
    }
    const host: SessionHost = {
      get stage() {
        return stageEl as HTMLElement;
      },
      setProgress(done, total) {
        progress = { completed: done, total };
      },
      showSummary() {
        finish();
      },
      clearStage() {
        stageEl?.replaceChildren();
      },
    };
    runner = new SessionRunner({
      session: toSession(current, node, todayIso()),
      registry: GAME_REGISTRY,
      storage,
      logger: runtime.logger,
      bus: runtime.bus,
      host,
      // The Mode hands the Game its player-facing wording; the Game never reads
      // the copy map itself (docs/concepts/ui-shell.md).
      config: {
        labels: {
          alsoValid: copyText("anagram-also-valid"),
          statTime: copyText("stat-time"),
          statInstinct: copyText("stat-instinct"),
          statRetries: copyText("stat-retries"),
          statStreak: copyText("summary-streak"),
          share: copyText("action-share"),
          shared: copyText("action-shared"),
          continueOn: copyText("action-continue"),
        },
        streak: storage.loadSave()?.streak ?? 0,
      },
    });
    void runner.start();
  });
</script>

{#if phase === "playing" && journey && activeNode}
  <!-- A subtree that forces a palette has to PAINT it. The tokens alone only
       change what `text-*` and `border-*` resolve to; the page background comes
       from the body, which is still on the reader's OS preference - so a themed
       screen without its own background is light ink on a dark page. -->
  <div class="min-h-dvh bg-bg text-text-primary" data-theme={journey.theme}>
    <SessionShell
      logger={runtime.logger}
      title={journey.titleTa}
      backLabel={copyText("journey-back-to-map")}
      settingsLabel={copyText("action-settings")}
      {progress}
      bind:stage={stageEl}
      onExit={stop}
    >
      {#snippet rail()}
        <p
          class="font-tamil text-sm font-semibold text-text-secondary"
          data-testid="journey-game-name"
        >
          {copyText(`game-${activeNode.gameId}-title`)}
        </p>
      {/snippet}
    </SessionShell>
  </div>
{:else if phase === "map" && journey}
  <div class="min-h-dvh bg-bg text-text-primary" data-theme={journey.theme}>
    <main
      class="mx-auto flex min-h-dvh w-full max-w-4xl flex-col gap-lg p-lg"
      data-testid="journey-shell"
    >
      <header class="flex flex-col items-center gap-xs pt-lg text-center">
        <h1 class="font-tamil text-2xl font-bold text-text-primary">{journey.titleTa}</h1>
        <p class="font-tamil text-sm text-text-secondary">{copyText("mode-journey-note")}</p>
      </header>

      <JourneyMap {journey} {states} onPlay={play} />

      <button
        type="button"
        class="mx-auto inline-flex items-center gap-xs rounded-lg px-lg py-md font-tamil text-text-secondary transition-transform duration-fast ease-spring hover:-translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        data-testid="journey-home"
        onclick={onHome}
      >
        <Glyph id="back" />
        {copyText("action-home")}
      </button>
    </main>
  </div>
{:else if phase === "unavailable"}
  <main
    class="flex min-h-dvh flex-col items-center justify-center gap-md p-lg text-center"
    data-testid="journey-unavailable"
  >
    <h1 class="font-tamil text-xl font-semibold text-text-primary">
      {copyText("journey-empty-title")}
    </h1>
    <p class="max-w-xs font-tamil text-text-secondary">{copyText("journey-empty-body")}</p>
    <button
      type="button"
      class="inline-flex items-center gap-xs rounded-lg bg-accent px-lg py-md font-tamil text-bg shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      onclick={onHome}
    >
      <Glyph id="back" />
      {copyText("action-home")}
    </button>
  </main>
{:else}
  <main
    class="flex min-h-dvh items-center justify-center p-lg"
    data-testid="journey-loading"
  >
    <p class="font-tamil text-text-secondary">{copyText("daily-loading")}</p>
  </main>
{/if}

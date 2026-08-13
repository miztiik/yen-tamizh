<script lang="ts">
  // Row 11 integration harness - the browser proof that the shell + runtime work
  // end to end: it wires a real Runtime, StorageService, a two-item fake Session,
  // the SessionShell, and the SessionRunner, then plays. Reached only via
  // `?harness=session`; it is scaffolding that Row 13 (Home + DailyMode) replaces
  // with the real Mode chrome, and it is the surface the e2e smoke drives.
  import SessionShell from "./SessionShell.svelte";
  import { createRuntime } from "../telemetry/runtime";
  import { StorageService } from "../services/StorageService";
  import { SessionRunner, type SessionHost } from "../session/SessionRunner";
  import { fakeGameFactory } from "../session/__fixtures__/fakeGame";
  import type { GameRegistry } from "../games/registry";
  import type { Session, SessionResult } from "../session/types";

  const runtime = createRuntime({ dev: import.meta.env.DEV });
  const storage = new StorageService({ store: localStorage });
  const registry: GameRegistry = { fake: { load: async () => fakeGameFactory } };

  const today = new Date().toISOString().slice(0, 10);
  const session: Session = {
    modeId: "harness",
    packId: "ta-core",
    gameId: "fake",
    sessionId: `harness-${today}`,
    date: today,
    items: [
      { gameId: "fake", payload: { label: "one", score: 1 } },
      { gameId: "fake", payload: { label: "two", score: 1 } },
    ],
  };

  let progress = $state<{ completed: number; total: number } | null>(null);
  let stageEl = $state<HTMLElement | undefined>();
  let started = false;

  function renderSummary(result: SessionResult): void {
    const stage = stageEl;
    if (stage === undefined) return;
    const panel = document.createElement("div");
    panel.setAttribute("data-testid", "session-summary");
    panel.className = "flex flex-col items-center gap-sm anim-pop";
    const heading = document.createElement("h2");
    heading.className = "font-display text-lg text-success";
    heading.textContent = "Session complete";
    const detail = document.createElement("p");
    detail.className = "text-text-secondary";
    detail.textContent = `${result.itemsCompleted}/${result.itemsTotal} - ${result.totalScore} points`;
    panel.append(heading, detail);
    stage.replaceChildren(panel);
  }

  // Start only once the shell's stage element is bound (the Game's mount target).
  $effect(() => {
    if (stageEl === undefined || started) return;
    started = true;
    const host: SessionHost = {
      get stage() {
        return stageEl as HTMLElement;
      },
      setProgress(completed, total) {
        progress = { completed, total };
      },
      showSummary(result) {
        renderSummary(result);
      },
      clearStage() {
        stageEl?.replaceChildren();
      },
    };
    const runner = new SessionRunner({
      session,
      registry,
      storage,
      logger: runtime.logger,
      bus: runtime.bus,
      host,
    });
    void runner.start();
  });
</script>

<SessionShell logger={runtime.logger} title="Session harness" {progress} bind:stage={stageEl} />

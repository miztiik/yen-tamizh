// A trivial fake Game used by the SessionRunner Oracle test and the Row 11
// browser harness. It exists to prove the runtime boundary, NOT to be fun:
//
//   - it implements the full GameModule contract (mount/destroy/get/restore);
//   - it imports ONLY the session types - never StorageService, never app
//     config - so it structurally cannot cross the single-writer or
//     payloads-not-calls boundaries (CLAUDE.md section 1a, Fowler);
//   - it reports progress by EMITTING catalog events through `ctx.logger`, which
//     is the exact path a real Game (Row 12 anagram) will use;
//   - its state (`{ placed }`) round-trips through getState/restoreState, so a
//     reload resumes mid-item.
//
// In a browser it renders clickable controls into `stage` (for the e2e); in a
// node test it just tracks state and the test calls the simulate* methods.

import type { GameContext, GameModule } from "../types";

export interface FakeGameState {
  placed: string[];
}

interface FakePayload {
  label?: string;
  /** Points awarded on completion (defaults to 1). */
  score?: number;
}

export class FakeGame implements GameModule<FakeGameState> {
  private ctx: GameContext | null = null;
  private stage: HTMLElement | null = null;
  private state: FakeGameState = { placed: [] };

  mount(stage: HTMLElement, ctx: GameContext): void {
    this.stage = stage;
    this.ctx = ctx;
    this.render();
    ctx.logger.emit("puzzle.started", { data: { label: this.label() } });
  }

  destroy(): void {
    this.stage = null;
    this.ctx = null;
  }

  getState(): FakeGameState {
    return { placed: [...this.state.placed] };
  }

  restoreState(state: FakeGameState): void {
    this.state = { placed: [...(state?.placed ?? [])] };
    this.render();
  }

  /** Simulate placing a tile: mutate state + emit an attempt (runner snapshots). */
  attempt(tile = `t${this.state.placed.length + 1}`): void {
    this.state.placed.push(tile);
    this.render();
    this.ctx?.logger.emit("puzzle.attempt.submitted", {
      data: { attemptIndex: this.state.placed.length, tile },
    });
  }

  /** Simulate solving the puzzle: emit completion (runner advances). */
  complete(): void {
    this.ctx?.logger.emit("puzzle.completed", {
      data: { score: this.score(), attempts: this.state.placed.length },
    });
  }

  /** Simulate giving up: emit abandonment (runner advances without a score). */
  abandon(): void {
    this.ctx?.logger.emit("puzzle.abandoned", { level: "warn", data: {} });
  }

  private label(): string {
    return (this.ctx?.payload as FakePayload | undefined)?.label ?? "item";
  }

  private score(): number {
    return (this.ctx?.payload as FakePayload | undefined)?.score ?? 1;
  }

  private render(): void {
    const stage = this.stage;
    if (stage === null) return;
    if (typeof document === "undefined") {
      // node: no DOM - a text marker is enough to show the Game rendered here.
      stage.textContent = `FAKE GAME - ${this.label()} - placed:${this.state.placed.length}`;
      return;
    }
    stage.replaceChildren();
    const wrap = document.createElement("div");
    wrap.setAttribute("data-testid", "fake-game");
    wrap.className = "flex flex-col items-center gap-sm";

    const label = document.createElement("p");
    label.className = "font-display text-text-primary";
    label.textContent = `Fake puzzle: ${this.label()}`;

    const placed = document.createElement("p");
    placed.setAttribute("data-testid", "fake-placed");
    placed.className = "text-text-secondary";
    placed.textContent = `placed: ${this.state.placed.length}`;

    const attemptBtn = document.createElement("button");
    attemptBtn.type = "button";
    attemptBtn.setAttribute("data-testid", "fake-attempt");
    attemptBtn.className =
      "rounded-md bg-bg-elevated px-md py-sm text-text-primary shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";
    attemptBtn.textContent = "Place tile";
    attemptBtn.addEventListener("click", () => this.attempt());

    const submitBtn = document.createElement("button");
    submitBtn.type = "button";
    submitBtn.setAttribute("data-testid", "fake-submit");
    submitBtn.className =
      "rounded-md bg-accent px-md py-sm text-bg shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";
    submitBtn.textContent = "Submit";
    submitBtn.addEventListener("click", () => this.complete());

    wrap.append(label, placed, attemptBtn, submitBtn);
    stage.append(wrap);
  }
}

/** A registry factory that builds a fresh FakeGame per item. */
export const fakeGameFactory = (): GameModule => new FakeGame();

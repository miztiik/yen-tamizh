// The crossword Game's runtime adapter: it binds the Svelte playing surface to
// the `GameModule` contract the SessionRunner drives (docs/concepts/ui-shell.md).
//
// The runner owns a plain `stage` element and knows nothing about Svelte, so the
// adapter is the only place the two meet: it mounts the component into `stage`,
// forwards `getState`/`restoreState` to the component's exports, and unmounts on
// teardown. Everything the Game is allowed to see - the payload, the scoped
// logger, the config slice, the clock - arrives as props from the GameContext,
// and nothing else is imported (the boundary `boundary.test.ts` enforces).

import { mount, unmount } from "svelte";

import type { GameContext, GameModule } from "../../session/types";

import { initialState, type CrosswordPayload, type CrosswordState } from "./logic";
import CrosswordGameView from "./CrosswordGame.svelte";

/** The component surface the adapter drives (the view's instance exports). */
interface CrosswordView {
  getState(): CrosswordState;
  restoreState(raw: unknown): void;
  dispose(): void;
}

class CrosswordGame implements GameModule<CrosswordState> {
  private view: CrosswordView | null = null;
  private last: CrosswordState = initialState();

  mount(stage: HTMLElement, ctx: GameContext): void {
    this.view = mount(CrosswordGameView, {
      target: stage,
      props: {
        payload: ctx.payload as CrosswordPayload,
        logger: ctx.logger,
        config: ctx.config,
        now: ctx.now,
      },
    }) as CrosswordView;
  }

  destroy(): void {
    const view = this.view;
    if (view === null) return;
    // Keep the last snapshot readable after teardown: the runner may persist
    // once more while advancing off this item.
    this.last = view.getState();
    view.dispose();
    this.view = null;
    void unmount(view);
  }

  getState(): CrosswordState {
    return this.view?.getState() ?? this.last;
  }

  restoreState(state: CrosswordState): void {
    this.view?.restoreState(state);
  }
}

/** Registry factory: a fresh Game per session item. */
export const crosswordGameFactory = (): GameModule => new CrosswordGame();

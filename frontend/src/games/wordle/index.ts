// The wordle Game's runtime adapter: it binds the Svelte playing surface to the
// `GameModule` contract the SessionRunner drives (docs/concepts/ui-shell.md).
//
// The runner owns a plain `stage` element and knows nothing about Svelte, so the
// adapter is the only place the two meet: it mounts the component into `stage`,
// forwards `getState`/`restoreState` to the component's exports, and unmounts on
// teardown. Everything the Game is allowed to see - the payload, the scoped
// logger, the config slice, the clock - arrives as props from the GameContext,
// and nothing else is imported (the boundary `boundary.test.ts` enforces).

import { mount, unmount } from "svelte";

import type { GameContext, GameModule } from "../../session/types";

import { initialState, type WordlePayload, type WordleState } from "./logic";
import WordleGameView from "./WordleGame.svelte";

/** The component surface the adapter drives (the view's instance exports). */
interface WordleView {
  getState(): WordleState;
  restoreState(raw: unknown): void;
  dispose(): void;
}

class WordleGame implements GameModule<WordleState> {
  private view: WordleView | null = null;
  private last: WordleState = initialState();

  mount(stage: HTMLElement, ctx: GameContext): void {
    this.view = mount(WordleGameView, {
      target: stage,
      props: {
        payload: ctx.payload as WordlePayload,
        logger: ctx.logger,
        config: ctx.config,
        now: ctx.now,
      },
    }) as WordleView;
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

  getState(): WordleState {
    return this.view?.getState() ?? this.last;
  }

  restoreState(state: WordleState): void {
    this.view?.restoreState(state);
  }
}

/** Registry factory: a fresh Game per session item. */
export const wordleGameFactory = (): GameModule => new WordleGame();

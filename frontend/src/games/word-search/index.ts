// The word-search Game's runtime adapter: it binds the Svelte playing surface to
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

import { initialState, type WordSearchPayload, type WordSearchState } from "./logic";
import WordSearchGameView from "./WordSearchGame.svelte";

/** The component surface the adapter drives (the view's instance exports). */
interface WordSearchView {
  getState(): WordSearchState;
  restoreState(raw: unknown): void;
  dispose(): void;
}

class WordSearchGame implements GameModule<WordSearchState> {
  private view: WordSearchView | null = null;
  private last: WordSearchState = initialState();

  mount(stage: HTMLElement, ctx: GameContext): void {
    this.view = mount(WordSearchGameView, {
      target: stage,
      props: {
        payload: ctx.payload as WordSearchPayload,
        logger: ctx.logger,
        config: ctx.config,
        now: ctx.now,
      },
    }) as WordSearchView;
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

  getState(): WordSearchState {
    return this.view?.getState() ?? this.last;
  }

  restoreState(state: WordSearchState): void {
    this.view?.restoreState(state);
  }
}

/** Registry factory: a fresh Game per session item. */
export const wordSearchGameFactory = (): GameModule => new WordSearchGame();

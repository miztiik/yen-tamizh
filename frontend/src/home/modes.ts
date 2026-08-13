// The Mode catalog the Home draws (docs/concepts/modes.md).
//
// These are IDENTIFIERS plus their presentation - never player-facing text. The
// title, the note, and the "coming soon" pill all come from `config/copy.json`,
// keyed by these slugs, so a Tamil wording change never touches a component.
//
// Every Mode in the catalog is listed whether or not it is switched on: the
// Home shows the whole shape of the game and marks what is not built yet, which
// is honest and tells a returning player what to expect (Palm). Which ones are
// PLAYABLE is `config/app-config.json`'s `ui.enabledModes`, not this list.

export interface ModeCard {
  readonly modeId: string;
  /** Glyph id from the baked manifest (Holy Law #10). */
  readonly glyphId: string;
  /** Copy slugs; `-title-en` is the small secondary line under the Tamil. */
  readonly titleSlug: string;
  readonly titleEnSlug: string;
  readonly noteSlug: string;
}

export const MODE_CARDS: readonly ModeCard[] = [
  {
    modeId: "daily",
    glyphId: "star",
    titleSlug: "mode-daily-title",
    titleEnSlug: "mode-daily-title-en",
    noteSlug: "mode-daily-note",
  },
  {
    modeId: "journey",
    glyphId: "star",
    titleSlug: "mode-journey-title",
    titleEnSlug: "mode-journey-title-en",
    noteSlug: "mode-journey-note",
  },
  {
    modeId: "infinite",
    glyphId: "star",
    titleSlug: "mode-infinite-title",
    titleEnSlug: "mode-infinite-title-en",
    noteSlug: "mode-infinite-note",
  },
  {
    modeId: "time-trial",
    glyphId: "star",
    titleSlug: "mode-time-trial-title",
    titleEnSlug: "mode-time-trial-title-en",
    noteSlug: "mode-time-trial-note",
  },
];

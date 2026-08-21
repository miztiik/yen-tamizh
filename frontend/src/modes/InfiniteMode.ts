// InfiniteMode - the endless Mode (docs/concepts/modes.md `infinite`).
//
// A Mode owns SESSION FRAMING and nothing else. Where DailyMode frames the day
// the calendar names and JourneyMode the node the player's progress names, this
// one frames the NEXT board of a stream that does not end - and the only reason
// it can do that with no runtime backend (Holy Law #1) is that every board it
// will ever deal was baked into the bundle at build time.
//
// Four rules shape it:
//
//   - NEVER FETCH THE POOL. The pool is ~1,800 files and 1.4 MB; a stream that
//     downloaded it to start would be exactly the thing Holy Law #2 forbids on
//     a mid-tier phone over patchy 4G. So the Mode fetches one small `index`
//     per Game (13.8 KB raw, 1.3 KB over the wire) and then ONE board at a time
//     (0.4-1.6 KB), which is what makes an endless mode cheaper than a day.
//   - SAME-ORIGIN ONLY, through `withBase` + `loadValidated`, so it works
//     offline, is schema-validated at the boundary, and never reaches a CDN.
//   - THE STREAM NEVER ENDS AND NEVER REPEATS ITSELF SOON. An unseen board is
//     always preferred; when every eligible board is inside the anti-repeat
//     window the stream RECYCLES the least recently seen one rather than
//     dead-ending. A player who has exhausted a band must still get a puzzle.
//   - THE SAVE IS THE ONLY AUTHORITY ON WHAT HAS BEEN SEEN, and it is bounded
//     (`config.infinite.lruWindow`, kept by StorageService).
//
// A stream item is ONE session of one item, like a Journey node: that is what
// lets the SessionRunner - which walks a finite list - drive something infinite,
// and it is also what makes "the player stopped after three" a fact the shell
// can state rather than a session it has to abandon.

import { loadValidated, type SchemaName, type SchemaPayload } from "../contracts";
import type { PoolIndex, PoolItem } from "../contracts";
import { withBase } from "../lib/base";
import type { Session } from "../session/types";

/** The Mode's stable identifier (the `modeId` in the save and in telemetry). */
export const INFINITE_MODE_ID = "infinite";

/** One line of a pool index, as the file spells it. */
export type PoolEntry = PoolIndex["items"][number];

/** The typed loader InfiniteMode needs; tests inject a local one (no network). */
export type ValidatedLoader = <K extends SchemaName>(
  url: string,
  schemaName: K,
) => Promise<SchemaPayload[K]>;

/** Where one Game's pool index lives, base-path aware. */
export function poolIndexUrl(gameId: string, base?: string): string {
  return withBase(`pool/${gameId}/index.json`, base);
}

/** Where one pooled board lives, base-path aware. */
export function poolItemUrl(gameId: string, id: string, base?: string): string {
  return withBase(`pool/${gameId}/${id}.json`, base);
}

/**
 * The key one board is remembered by in `save.seenInfiniteIds`.
 *
 * Game-qualified, because a pool id is only an ordinal inside its own Game and
 * `00042` names six different boards. It reads like the path it came from so a
 * save is inspectable by a human.
 */
export function seenKey(gameId: string, id: string): string {
  return `${gameId}/${id}`;
}

/** The pool entries a difficulty filter admits, in index order. */
export function eligible(index: PoolIndex, difficulty: string): PoolEntry[] {
  return index.items.filter((entry) => entry.difficulty === difficulty);
}

/**
 * The next board to deal from one Game's pool, or `null` when the filter
 * admits none of it.
 *
 * THE ANTI-REPEAT RULE, stated once. The first eligible board the window has
 * not seen wins - in INDEX order, which is not an arbitrary walk: a pool is
 * baked in a frequency-stratified draw, so any prefix of a band is a
 * proportional sample of how familiar its words are, and taking them in order
 * is what keeps a player's first dozen from being the rarest dozen.
 *
 * When the window has seen every eligible board, the stream recycles the LEAST
 * RECENTLY seen one instead of dead-ending. That is the documented
 * pool-exhaustion behaviour and it is the only one that keeps the Mode's
 * promise: a player who has worked through a whole band deserves the board they
 * met longest ago, not an apology. `seenInfiniteIds` is ordered oldest-first,
 * so "least recently seen" is simply the earliest position in it.
 */
export function pickNext(
  index: PoolIndex,
  difficulty: string,
  seen: readonly string[],
): string | null {
  const pool = eligible(index, difficulty);
  if (pool.length === 0) return null;
  const seenAt = new Map(seen.map((key, position) => [key, position]));
  const fresh = pool.find((entry) => !seenAt.has(seenKey(index.gameId, entry.id)));
  if (fresh !== undefined) return fresh.id;

  let oldest = pool[0] as PoolEntry;
  let oldestAt = Number.POSITIVE_INFINITY;
  for (const entry of pool) {
    const at = seenAt.get(seenKey(index.gameId, entry.id)) ?? -1;
    if (at < oldestAt) {
      oldestAt = at;
      oldest = entry;
    }
  }
  return oldest.id;
}

/** Frame one pooled board as a Session the runner can walk. */
export function toSession(item: PoolItem, date: string): Session {
  return {
    modeId: INFINITE_MODE_ID,
    packId: item.packId,
    gameId: item.gameId,
    // Unique per board, so the runner never restores a finished board's
    // snapshot into the next one (SessionRunner's `sessionId` check).
    sessionId: `${INFINITE_MODE_ID}-${item.gameId}-${item.id}`,
    date,
    items: [{ gameId: item.gameId, payload: item.payload }],
  };
}

/** One dealt board: what it is, and the session that plays it. */
export interface StreamStep {
  gameId: string;
  id: string;
  /** The key to record in `save.seenInfiniteIds`. */
  seenKey: string;
  difficulty: string;
  session: Session;
}

/** What the shell gets back: the next board, or a reason there is none. */
export type StreamOutcome =
  | { status: "ready"; step: StreamStep }
  | { status: "unavailable"; reason: "load-failed" | "empty-pool" };

export interface InfiniteStreamDeps {
  /** The Games the stream rotates through - `config.daily.games`. */
  games: readonly string[];
  /** The player's local calendar day (the save's `dayKey` is derived from it). */
  date: string;
  /** Starting filter; `config.infinite.defaultDifficulty`. */
  difficulty: string;
  /** Read the CURRENT seen list - a function, because the shell writes to it. */
  seen: () => readonly string[];
  /** Defaults to the schema-validating same-origin fetch. */
  load?: ValidatedLoader;
  /** Defaults to the bundle's base path. */
  base?: string;
}

/**
 * The endless stream itself.
 *
 * A small object rather than a pure function, because the one thing worth
 * keeping between boards is the per-Game index: fetching it again for every
 * puzzle would turn a 1.3 KB start-up cost into a 1.3 KB per-board cost, which
 * is most of what a board costs. Everything that DECIDES anything is a pure
 * function above, and this only sequences them.
 *
 * The Games rotate rather than being chosen, so an endless mode is a variety of
 * boards instead of three hundred of the same one (Palm). A Game whose pool
 * will not load, or holds nothing at the current difficulty, is stepped over -
 * one bad file must not end the stream.
 */
export class InfiniteStream {
  private readonly deps: InfiniteStreamDeps;
  private readonly load: ValidatedLoader;
  private readonly indexes = new Map<string, PoolIndex>();
  private difficulty: string;
  private cursor = 0;

  constructor(deps: InfiniteStreamDeps) {
    this.deps = deps;
    this.load = deps.load ?? loadValidated;
    this.difficulty = deps.difficulty;
  }

  /** The filter in force right now. */
  get band(): string {
    return this.difficulty;
  }

  /** Change the difficulty filter; the next board honours it. */
  setDifficulty(difficulty: string): void {
    this.difficulty = difficulty;
  }

  /** Deal the next board. Never throws. */
  async next(): Promise<StreamOutcome> {
    const { games } = this.deps;
    if (games.length === 0) return { status: "unavailable", reason: "empty-pool" };
    let reachedAPool = false;
    // Bounded by the ring, so a difficulty no pool holds ends in an answer
    // rather than a spin.
    for (let attempt = 0; attempt < games.length; attempt += 1) {
      const gameId = games[(this.cursor + attempt) % games.length] as string;
      const index = await this.indexOf(gameId);
      if (index === null) continue;
      reachedAPool = true;
      const id = pickNext(index, this.difficulty, this.deps.seen());
      if (id === null) continue;
      const item = await this.itemOf(gameId, id);
      if (item === null) continue;
      this.cursor = (this.cursor + attempt + 1) % games.length;
      return {
        status: "ready",
        step: {
          gameId,
          id,
          seenKey: seenKey(gameId, id),
          difficulty: item.difficulty,
          session: toSession(item, this.deps.date),
        },
      };
    }
    return { status: "unavailable", reason: reachedAPool ? "empty-pool" : "load-failed" };
  }

  private async indexOf(gameId: string): Promise<PoolIndex | null> {
    const cached = this.indexes.get(gameId);
    if (cached !== undefined) return cached;
    try {
      const index = await this.load(poolIndexUrl(gameId, this.deps.base), "pool-index");
      this.indexes.set(gameId, index);
      return index;
    } catch {
      return null;
    }
  }

  private async itemOf(gameId: string, id: string): Promise<PoolItem | null> {
    try {
      return await this.load(poolItemUrl(gameId, id, this.deps.base), "pool-item");
    } catch {
      return null;
    }
  }
}

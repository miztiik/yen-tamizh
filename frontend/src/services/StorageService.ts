// StorageService - the ONE writer to browser persistence (docs/concepts/
// ui-shell.md "StorageService"). Games and Modes never touch storage; they emit
// events and the SessionRunner hands state here. Every key is prefixed `yt:`.
//
// The persisted surface is the Row 7 `save` schema. We validate on write (fail
// fast at the boundary - refuse to persist a malformed save) and on read (a
// corrupt or unreadable save is treated as absent, so a bad payload never bricks
// the app; the read side is where a future breaking-change migration will land -
// `save` is the one migrating surface, docs/architecture/contracts/schemas.md).
//
// The store is injected (a `KeyValueStore`): `localStorage` satisfies it at
// runtime, and a unit test passes an in-memory fake - no DOM, no wrapper library
// (Holy Law #8: no new dependency where the raw Web API suffices).

import Ajv2020 from "ajv/dist/2020";

import saveSchema from "../contracts/save.schema.json";
import type { Save } from "../contracts/save";

import { dayKeyOf, type DayContext } from "../session/dayKey";
import { previousDayIso } from "../lib/dates";
import type { SessionState } from "../session/types";

/** The minimal key-value surface StorageService needs; `localStorage` fits. */
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const KEY_PREFIX = "yt:";
const SAVE_KEY = `${KEY_PREFIX}save`;

/**
 * Where a Mode's day-independent progress lives inside `perMode`.
 *
 * Derived in one place so two callers cannot pick keys that collide, and kept
 * inside the `perMode` map rather than beside it so the save schema still says
 * what it has always said: progress is keyed by Mode.
 */
function progressKeyOf(modeId: string): string {
  return `${modeId}-progress`;
}

/** What one streak tick did: the run before, after, and whether it moved. */
export interface StreakTick {
  before: number;
  after: number;
  ticked: boolean;
}

// The save-contract version this frontend writes. Mirrors the newest entry of
// schemas/save.schema.json's changelog; bump both together when the save shape
// changes (and add the read-side migration). ajv validates the date pattern +
// changelog shape on every write, so a malformed stamp is caught immediately.
const SAVE_VERSION = "2026-08-13T20:08";
const SAVE_CHANGELOG: Save["changelog"] = [
  {
    version: SAVE_VERSION,
    change: "Added the optional lastStreakDay marker.",
    why: "Row 13 - the streak ticks once per COMPLETED day, so it needs a marker of its own; lastPlayed moves on every write and cannot answer that question.",
  },
  {
    version: "2026-08-13",
    change: "Initial browser-written save.",
    why: "Row 11 StorageService writes the save surface.",
  },
];

// One draft 2020-12 validator for the save surface, compiled from the generated
// schema (same bytes the backend exports; the CI drift gate keeps them in sync).
const ajv = new Ajv2020({ allErrors: true });
const validateSave = ajv.compile<Save>(saveSchema);

export class StorageService {
  private readonly store: KeyValueStore;

  constructor(deps: { store: KeyValueStore }) {
    this.store = deps.store;
  }

  /** Read + validate the save, or `null` if absent, corrupt, or invalid. */
  loadSave(): Save | null {
    const raw = this.store.getItem(SAVE_KEY);
    if (raw === null) return null;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return null; // corrupt bytes -> treat as no save (fail safe)
    }
    if (!validateSave(parsed)) return null; // wrong shape -> fail safe
    return parsed;
  }

  /** Validate then persist a save; throws on an invalid shape (fail fast). */
  writeSave(save: Save): void {
    if (!validateSave(save)) {
      throw new Error(
        `StorageService: refusing to write an invalid save - ${ajv.errorsText(validateSave.errors)}`,
      );
    }
    this.store.setItem(SAVE_KEY, JSON.stringify(save));
  }

  /**
   * The current session state for a Mode, or `null` if there is nothing to
   * resume today. The day is decided by recomputing from the value fields
   * (`ctx.date`), NOT by trusting the stored `dayKey` - a save from another day
   * does not resume (docs/agents/guardrails.md derived-key rule).
   */
  readSessionState(ctx: DayContext): SessionState | null {
    const save = this.loadSave();
    if (save === null) return null;
    if (save.lastPlayed !== ctx.date) return null; // new day -> start fresh
    const record = save.perMode[ctx.modeId];
    if (record === undefined) return null;
    return record as unknown as SessionState;
  }

  /** Upsert a Mode's session state, stamping a freshly recomputed `dayKey`. */
  writeSessionState(ctx: DayContext, state: SessionState): void {
    const base = this.loadSave() ?? this.freshSave(ctx);
    const next: Save = {
      ...base,
      version: SAVE_VERSION,
      changelog: SAVE_CHANGELOG,
      dayKey: dayKeyOf(ctx), // recomputed + authoritative; never the stored one
      lastPlayed: ctx.date,
      perMode: {
        ...base.perMode,
        [ctx.modeId]: state as unknown as Record<string, unknown>,
      },
    };
    this.writeSave(next);
  }

  /**
   * A Mode's DAY-INDEPENDENT record, or `null` when there is none.
   *
   * Two Modes want two different things out of `perMode` and only one of them
   * is about today. A Daily day expires - `readSessionState` refuses a record
   * from another date, which is what makes yesterday's half-finished day stop
   * offering itself - while a Journey's progress is the whole point of the Mode
   * and must survive every date. So they get SEPARATE keys: this one is
   * `<modeId>-progress`, and the split is structural rather than a convention,
   * because `writeSessionState` REPLACES `perMode[modeId]` wholesale and would
   * otherwise wipe the path's progress every time the runner snapshotted a
   * puzzle.
   *
   * The value is returned as an open record: what a Mode keeps in it is the
   * Mode's business, and it arrives from storage untrusted, so the reader is
   * expected to parse it defensively rather than cast it.
   */
  readModeProgress(modeId: string): Record<string, unknown> | null {
    const save = this.loadSave();
    if (save === null) return null;
    return save.perMode[progressKeyOf(modeId)] ?? null;
  }

  /** Upsert a Mode's day-independent progress record. */
  writeModeProgress(ctx: DayContext, progress: Record<string, unknown>): void {
    const base = this.loadSave() ?? this.freshSave(ctx);
    this.writeSave({
      ...base,
      version: SAVE_VERSION,
      changelog: SAVE_CHANGELOG,
      dayKey: dayKeyOf(ctx),
      lastPlayed: ctx.date,
      perMode: { ...base.perMode, [progressKeyOf(ctx.modeId)]: progress },
    });
  }

  /**
   * Tick the streak for a COMPLETED day - once, however many times the day is
   * finished (Palm: one tick per day, never per item; re-opening a finished day
   * must not inflate it). `lastStreakDay` is the marker that makes it
   * idempotent: `lastPlayed` moves on every save and cannot answer "has this
   * day already counted?".
   *
   * A gap breaks the run: finishing after skipping a day starts again at 1,
   * which is the honest reading of a streak.
   */
  tickStreak(ctx: DayContext): StreakTick {
    const save = this.loadSave() ?? this.freshSave(ctx);
    const before = save.streak;
    if (save.lastStreakDay === ctx.date) return { before, after: before, ticked: false };

    const after = save.lastStreakDay === previousDayIso(ctx.date) ? before + 1 : 1;
    this.writeSave({
      ...save,
      version: SAVE_VERSION,
      changelog: SAVE_CHANGELOG,
      dayKey: dayKeyOf(ctx),
      streak: after,
      lastStreakDay: ctx.date,
      lastPlayed: ctx.date,
    });
    return { before, after, ticked: true };
  }

  /** The pool items the Infinite stream has already dealt, oldest first. */
  readSeenInfiniteIds(): string[] {
    return this.loadSave()?.seenInfiniteIds ?? [];
  }

  /**
   * Record one dealt pool item, keeping `seenInfiniteIds` an LRU bounded by
   * `window` (`config.infinite.lruWindow`).
   *
   * Three properties, and each is load-bearing for the anti-repeat claim:
   *
   *   - It is a LEAST-RECENTLY-USED list, not a set with a cap. Re-dealing an
   *     id MOVES it to the end rather than leaving it where it was, which is
   *     what makes "the oldest one is the fairest to show again" a true
   *     statement about the front of the list.
   *   - It is bounded, so a player who never stops does not grow their save
   *     without limit. The bound is passed in rather than read here: the window
   *     is a config knob and StorageService reads no config (it is the writer,
   *     not a policy).
   *   - It is recorded when a board is DEALT, not when it is solved. A puzzle
   *     the player abandoned has still been seen, and offering it again as if
   *     it were new would be the repeat the window exists to prevent.
   *
   * The bound is applied with an explicit length arithmetic rather than
   * `slice(-window)`, because `slice(-0)` returns the WHOLE array and a window
   * of zero must mean "remember nothing".
   */
  markInfiniteSeen(ctx: DayContext, id: string, window: number): string[] {
    const base = this.loadSave() ?? this.freshSave(ctx);
    const promoted = [...base.seenInfiniteIds.filter((seen) => seen !== id), id];
    const bounded =
      window <= 0 ? [] : promoted.slice(Math.max(0, promoted.length - window));
    this.writeSave({
      ...base,
      version: SAVE_VERSION,
      changelog: SAVE_CHANGELOG,
      dayKey: dayKeyOf(ctx),
      lastPlayed: ctx.date,
      seenInfiniteIds: bounded,
    });
    return bounded;
  }

  private freshSave(ctx: DayContext): Save {
    return {
      version: SAVE_VERSION,
      changelog: SAVE_CHANGELOG,
      dayKey: dayKeyOf(ctx),
      streak: 0,
      lastPlayed: ctx.date,
      perMode: {},
      seenInfiniteIds: [],
    };
  }
}

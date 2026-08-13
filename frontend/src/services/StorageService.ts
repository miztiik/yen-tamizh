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
import type { SessionState } from "../session/types";

/** The minimal key-value surface StorageService needs; `localStorage` fits. */
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const KEY_PREFIX = "yt:";
const SAVE_KEY = `${KEY_PREFIX}save`;

// The save-contract version this frontend writes. Mirrors the newest entry of
// schemas/save.schema.json's changelog; bump both together when the save shape
// changes (and add the read-side migration). ajv validates the date pattern +
// changelog shape on every write, so a malformed stamp is caught immediately.
const SAVE_VERSION = "2026-08-13";
const SAVE_CHANGELOG: Save["changelog"] = [
  {
    version: SAVE_VERSION,
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

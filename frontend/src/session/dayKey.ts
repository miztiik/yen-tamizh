// The save `dayKey` - a DERIVED key, recomputed on read from its value fields
// and never trusted from storage (docs/agents/guardrails.md derived-key rule;
// docs/concepts/ui-shell.md). This is the TypeScript twin of the backend's
// `compute_day_key` (backend/yen_tamizh_backend/contracts/save.py); the two must
// produce byte-identical keys, proven by dayKey.test.ts against the shared
// save fixture.

/** The value fields a `dayKey` is rebuilt from. */
export interface DayContext {
  readonly date: string;
  readonly modeId: string;
  readonly gameId: string;
  readonly packId: string;
}

/**
 * Rebuild the save `dayKey` from its value fields. The key is
 * `date|modeId|gameId|packId`; a reader recomputes it on every read so a stale
 * or tampered stored key can never select the wrong day's progress.
 */
export function computeDayKey(
  date: string,
  modeId: string,
  gameId: string,
  packId: string,
): string {
  return `${date}|${modeId}|${gameId}|${packId}`;
}

/** Convenience overload over a {@link DayContext}. */
export function dayKeyOf(ctx: DayContext): string {
  return computeDayKey(ctx.date, ctx.modeId, ctx.gameId, ctx.packId);
}

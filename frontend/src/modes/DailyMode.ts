// DailyMode - the calendar-bound Mode (docs/concepts/modes.md `daily`).
//
// A Mode owns SESSION FRAMING and nothing else: it supplies an ordered list of
// items and the day they belong to, and the SessionRunner plays them. This one
// frames a day that the build-time generator already baked, so it does no
// puzzle generation of its own - it reads `bank/index.json`, opens the right
// day, and hands the runner what it finds.
//
// Two rules shape it:
//
//   - SAME-ORIGIN ONLY. The bank ships inside the bundle under `public/bank/`
//     and is read through `withBase` + `loadValidated`, so it works offline, is
//     schema-validated at the boundary, and never reaches a CDN (Holy Law #1).
//   - NEVER A BLANK SCREEN. A missing day, an unreachable file, or a payload
//     that fails its schema all resolve to an `unavailable` outcome the shell
//     can render as a sentence, not an exception (Player: a broken screen is a
//     reason to delete the app).

import { loadValidated, type SchemaName, type SchemaPayload } from "../contracts";
import type { BankIndex, PuzzleFile } from "../contracts";
import { withBase } from "../lib/base";
import type { Session } from "../session/types";

/** The Mode's stable identifier (the `modeId` in the save and in telemetry). */
export const DAILY_MODE_ID = "daily";

/** The typed loader DailyMode needs; tests inject a local one (no network). */
export type ValidatedLoader = <K extends SchemaName>(
  url: string,
  schemaName: K,
) => Promise<SchemaPayload[K]>;

export interface DailyModeDeps {
  /** The player's local calendar day (YYYY-MM-DD). */
  today: string;
  /** Defaults to the schema-validating same-origin fetch. */
  load?: ValidatedLoader;
  /** Defaults to the bundle's base path. */
  base?: string;
}

/** What the shell gets back: a playable session, or a reason there is none. */
export type DailyOutcome =
  | {
      status: "ready";
      session: Session;
      /** The day actually opened - not always `today` (see `isToday`). */
      date: string;
      /** False when the bank's newest day is behind the player's calendar. */
      isToday: boolean;
    }
  | { status: "unavailable"; reason: "empty-bank" | "no-day" | "load-failed" };

/** Where the bank index lives, base-path aware. */
export function bankIndexUrl(base?: string): string {
  return withBase("bank/index.json", base);
}

/** Where one day's puzzle file lives, base-path aware. */
export function bankDayUrl(date: string, base?: string): string {
  return withBase(`bank/${date.slice(0, 4)}/${date}.json`, base);
}

/**
 * The day to play: today when the bank has it, else the newest baked day BEFORE
 * today. Falling back keeps a player who has not updated in a week - or whose
 * clock runs ahead of the cron - in a real puzzle instead of an apology. A day
 * in the FUTURE is never opened: tomorrow's puzzle is baked, but it is not
 * tomorrow yet.
 */
export function pickDay(index: BankIndex, today: string): string | null {
  const playable = index.days
    .map((day) => day.date)
    .filter((date) => date <= today)
    .sort();
  return playable[playable.length - 1] ?? null;
}

/** Frame one baked day as a Session the runner can walk. */
export function toSession(puzzleFile: PuzzleFile, date: string): Session {
  const first = puzzleFile.items[0];
  return {
    modeId: DAILY_MODE_ID,
    // A day is single-pack and (today) single-Game; the first item names both,
    // and they become part of the save's day key.
    packId: first?.packId ?? "ta-core",
    gameId: first?.gameId ?? "anagram",
    sessionId: `${DAILY_MODE_ID}-${date}`,
    date,
    items: puzzleFile.items.map((item) => ({
      gameId: item.gameId,
      payload: item.payload,
    })),
  };
}

/** Load today's session from the baked bank; never throws. */
export async function loadDailySession(deps: DailyModeDeps): Promise<DailyOutcome> {
  const load = deps.load ?? loadValidated;
  let index: BankIndex;
  try {
    index = await load(bankIndexUrl(deps.base), "bank-index");
  } catch {
    return { status: "unavailable", reason: "load-failed" };
  }
  if (index.days.length === 0) return { status: "unavailable", reason: "empty-bank" };

  const date = pickDay(index, deps.today);
  if (date === null) return { status: "unavailable", reason: "no-day" };

  let puzzleFile: PuzzleFile;
  try {
    puzzleFile = await load(bankDayUrl(date, deps.base), "puzzle-file");
  } catch {
    return { status: "unavailable", reason: "load-failed" };
  }
  if (puzzleFile.items.length === 0) {
    return { status: "unavailable", reason: "no-day" };
  }
  return {
    status: "ready",
    session: toSession(puzzleFile, date),
    date,
    isToday: date === deps.today,
  };
}

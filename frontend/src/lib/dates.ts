// Calendar-day helpers. The daily bank is keyed by YYYY-MM-DD, so every date
// the app computes has to agree on which day it is - and on which day came
// before it.
//
// "Today" is the player's LOCAL day, not UTC: a player in Chennai who opens the
// app after midnight is on tomorrow's date hours before UTC agrees, and telling
// them "no puzzle today" would be wrong on their own calendar. The generator
// bakes several days ahead precisely so the local day is always in the bank.
//
// Date arithmetic goes through UTC so a DST shift can never add or drop a day.

/** The local calendar day as YYYY-MM-DD. */
export function todayIso(now: Date = new Date()): string {
  const year = now.getFullYear();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** The day before a YYYY-MM-DD date, as YYYY-MM-DD. */
export function previousDayIso(date: string): string {
  const parsed = Date.parse(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed)) return date;
  return new Date(parsed - 86_400_000).toISOString().slice(0, 10);
}

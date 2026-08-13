/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

/**
 * @minItems 1
 */
export type Changelog = [ChangelogEntry, ...(ChangelogEntry)[]]
export type Change = string
export type Version = string
export type Why = string
export type Level = ("debug" | "info" | "warn" | "error")
export type Name = ("puzzle.started" | "puzzle.attempt.submitted" | "puzzle.hint.used" | "puzzle.completed" | "puzzle.abandoned" | "mode.session.started" | "mode.session.completed" | "streak.updated" | "pipeline.stage.started" | "pipeline.stage.completed" | "pipeline.stage.failed" | "puzzle.generated" | "bank.updated")
export type Session = string
export type Src = string
export type Ts = number
export type V = number
export type Version1 = string

/**
 * One structured telemetry event; ``name`` is from the canonical catalog.
 * 
 * ``ctx`` (stable context: modeId, gameId, packId, day) and ``data`` (the
 * event-specific payload) are open objects on purpose: their keys vary by
 * event, so pinning them would force a schema bump every time a Game emits a
 * new context key - which fights the "a Game is observable for free" design.
 * The fixed, typed part is the envelope; ``ctx`` and ``data`` are the open part.
 */
export interface EventEnvelope {
changelog: Changelog
ctx: Ctx
data: Data
level: Level
name: Name
session: Session
src: Src
ts: Ts
v: V
version: Version1
}
/**
 * One dated entry in a schema's in-file change log (newest first).
 * 
 * ``version`` is the date-stamp of the change; ``change`` is what changed;
 * ``why`` is the reason it changed (CLAUDE.md section 11).
 */
export interface ChangelogEntry {
change: Change
version: Version
why: Why
}
export interface Ctx {
[k: string]: unknown
}
export interface Data {
[k: string]: unknown
}

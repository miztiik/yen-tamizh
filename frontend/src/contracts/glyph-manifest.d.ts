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
export type Path = string
export type Viewbox = string
export type Version1 = string

/**
 * The baked index of every UI glyph, keyed by its lower-case slug id.
 */
export interface GlyphManifest {
changelog: Changelog
glyphs: Glyphs
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
export interface Glyphs {
[k: string]: GlyphShape
}
/**
 * One glyph's renderable geometry: a ``viewBox`` and a single ``path`` d.
 * 
 * This interface was referenced by `Glyphs`'s JSON-Schema definition
 * via the `patternProperty` "^[a-z][a-z0-9-]*$".
 */
export interface GlyphShape {
path: Path
viewBox: Viewbox
}

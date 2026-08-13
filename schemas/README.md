# schemas/

**Last Updated**: 2026-07-29

Typed JSON Schemas for every persisted surface in yen-tamizh (Holy Law #3,
`CLAUDE.md` sections 3 and 11). A contract lands here *before* the logic that
reads or writes it.

Each schema is a single flat file `schemas/<name>.schema.json` that carries:

- a `version` date-stamp (`YYYY-MM-DD`, never an integer or epoch), and
- a `changelog` array (newest entry first) of `{ version, change, why }`.

`$id` is the schema's relative path (`<name>.schema.json`) so offline IDE
JSON-Schema plugins validate without a network call.

The schemas are generated from the backend's Pydantic models (the single source
of truth) by the evolutionary contract pipeline; a CI drift gate regenerates and
fails on any diff. The pipeline and the first real schemas land in later rows -
this directory is a placeholder until then.

## See also

- [`../CLAUDE.md`](../CLAUDE.md) - section 11 (schema versioning), Holy Law #3.
- [`../docs/agents/guardrails.md`](../docs/agents/guardrails.md) - schema-versioning rules digest.

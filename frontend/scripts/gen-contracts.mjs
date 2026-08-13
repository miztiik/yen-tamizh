// Generate the frontend's contract artifacts from the backend-exported schemas.
//
// The backend Pydantic models are the single source of truth (Row 5). This
// script is the frontend half of the pipeline: for each
// schemas/<name>.schema.json it writes, under src/contracts/:
//   - <name>.d.ts        TypeScript types (via json-schema-to-typescript)
//   - <name>.schema.json a byte-copy of the schema, bundled so ajv can compile
//                        a validator from it at runtime
//
// Output is deterministic - LF line endings, a fixed banner, the schema list
// sorted, and NO external formatter (format:false removes prettier, whose
// version would otherwise vary between the author and CI) - so the CI drift
// gate reproduces the committed bytes exactly.
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import jsonSchemaToTypescript from "json-schema-to-typescript";

const { compile } = jsonSchemaToTypescript;

const here = dirname(fileURLToPath(import.meta.url));
const schemasDir = resolve(here, "../../schemas");
const outDir = resolve(here, "../src/contracts");

const BANNER = [
  "/* eslint-disable */",
  "/**",
  " * DO NOT EDIT. Generated from schemas/<name>.schema.json by",
  " * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,",
  " * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,",
  " * re-run the exporter, then re-run `npm run gen:contracts`.",
  " */",
].join("\n");

const toLF = (text) => text.replace(/\r\n/g, "\n");
const withTrailingNewline = (text) => (text.endsWith("\n") ? text : `${text}\n`);

const schemaFiles = readdirSync(schemasDir)
  .filter((name) => name.endsWith(".schema.json"))
  .sort();

mkdirSync(outDir, { recursive: true });

for (const file of schemaFiles) {
  const name = file.replace(/\.schema\.json$/, "");
  const raw = withTrailingNewline(toLF(readFileSync(resolve(schemasDir, file), "utf-8")));

  // 1. Byte-copy the schema into the frontend tree so index.ts can import it
  //    and ajv can compile a validator from it at runtime.
  writeFileSync(resolve(outDir, file), raw, "utf-8");

  // 2. Types. format:false keeps prettier (an external, version-sensitive
  //    formatter) out of the pipeline so the output is reproducible on CI.
  const types = await compile(JSON.parse(raw), name, {
    bannerComment: BANNER,
    format: false,
    additionalProperties: false,
  });
  writeFileSync(resolve(outDir, `${name}.d.ts`), withTrailingNewline(toLF(types)), "utf-8");
}

console.log(`gen-contracts: wrote ${schemaFiles.length} schema(s) to frontend/src/contracts/`);

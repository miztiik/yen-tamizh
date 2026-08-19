import Ajv2020 from "ajv/dist/2020";
import type { ValidateFunction } from "ajv";

import anagramPuzzleSchema from "./anagram-puzzle.schema.json";
import appConfigSchema from "./app-config.schema.json";
import bankIndexSchema from "./bank-index.schema.json";
import copySchema from "./copy.schema.json";
import eventEnvelopeSchema from "./event-envelope.schema.json";
import exampleSchema from "./example.schema.json";
import missingLettersPuzzleSchema from "./missing-letters-puzzle.schema.json";
import puzzleFileSchema from "./puzzle-file.schema.json";
import saveSchema from "./save.schema.json";
import wordlePuzzleSchema from "./wordle-puzzle.schema.json";
import type { AnagramPuzzle } from "./anagram-puzzle";
import type { AppConfig } from "./app-config";
import type { BankIndex } from "./bank-index";
import type { Copy } from "./copy";
import type { EventEnvelope } from "./event-envelope";
import type { Example } from "./example";
import type { MissingLettersPuzzle } from "./missing-letters-puzzle";
import type { PuzzleFile } from "./puzzle-file";
import type { Save } from "./save";
import type { WordlePuzzle } from "./wordle-puzzle";

// One draft 2020-12 validator instance for every generated contract. The
// <name>.schema.json files are byte-copies of the backend-exported
// schemas/<name>.schema.json (see scripts/gen-contracts.mjs); compiling them
// here yields runtime validators whose shape can never drift from the Pydantic
// source of truth (guaranteed by the CI drift gate).
const ajv = new Ajv2020({ allErrors: true });

const validators = {
  "anagram-puzzle": ajv.compile<AnagramPuzzle>(anagramPuzzleSchema),
  "app-config": ajv.compile<AppConfig>(appConfigSchema),
  "bank-index": ajv.compile<BankIndex>(bankIndexSchema),
  copy: ajv.compile<Copy>(copySchema),
  "event-envelope": ajv.compile<EventEnvelope>(eventEnvelopeSchema),
  example: ajv.compile<Example>(exampleSchema),
  "missing-letters-puzzle": ajv.compile<MissingLettersPuzzle>(missingLettersPuzzleSchema),
  "puzzle-file": ajv.compile<PuzzleFile>(puzzleFileSchema),
  save: ajv.compile<Save>(saveSchema),
  "wordle-puzzle": ajv.compile<WordlePuzzle>(wordlePuzzleSchema),
} as const;

/** Names of the generated contracts that can be validated at the boundary. */
export type SchemaName = keyof typeof validators;

/** The validated payload type for each contract name. */
export interface SchemaPayload {
  "anagram-puzzle": AnagramPuzzle;
  "app-config": AppConfig;
  "bank-index": BankIndex;
  copy: Copy;
  "event-envelope": EventEnvelope;
  example: Example;
  "missing-letters-puzzle": MissingLettersPuzzle;
  "puzzle-file": PuzzleFile;
  save: Save;
  "wordle-puzzle": WordlePuzzle;
}

/**
 * Fetch JSON same-origin and validate it against the named generated schema,
 * throwing a clear error on invalid data.
 *
 * This is the frontend's typed load-boundary (CLAUDE.md section 1a, "payloads
 * not calls"): the game consumes backend output only as schema-validated
 * payloads and fails fast at the boundary rather than trusting the bytes.
 */
export async function loadValidated<K extends SchemaName>(
  url: string,
  schemaName: K,
): Promise<SchemaPayload[K]> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`loadValidated: GET ${url} -> ${response.status}`);
  }
  const data: unknown = await response.json();
  const validate = validators[schemaName] as ValidateFunction<SchemaPayload[K]>;
  if (!validate(data)) {
    throw new Error(
      `loadValidated: payload for "${schemaName}" failed ${schemaName}.schema.json: ` +
        ajv.errorsText(validate.errors),
    );
  }
  return data;
}

export type {
  AnagramPuzzle,
  AppConfig,
  BankIndex,
  Copy,
  EventEnvelope,
  Example,
  PuzzleFile,
  Save,
  WordlePuzzle,
};

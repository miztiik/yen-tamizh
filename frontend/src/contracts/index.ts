import Ajv2020 from "ajv/dist/2020";
import type { ValidateFunction } from "ajv";

import exampleSchema from "./example.schema.json";
import type { Example } from "./example";

// One draft 2020-12 validator instance for every generated contract. The
// <name>.schema.json files are byte-copies of the backend-exported
// schemas/<name>.schema.json (see scripts/gen-contracts.mjs); compiling them
// here yields runtime validators whose shape can never drift from the Pydantic
// source of truth (guaranteed by the CI drift gate).
const ajv = new Ajv2020({ allErrors: true });

const validators = {
  example: ajv.compile<Example>(exampleSchema),
} as const;

/** Names of the generated contracts that can be validated at the boundary. */
export type SchemaName = keyof typeof validators;

/** The validated payload type for each contract name. */
export interface SchemaPayload {
  example: Example;
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

export type { Example };

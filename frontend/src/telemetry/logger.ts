// The structured logger - the ONLY way a Game or Mode is allowed to record an
// event (no console.log, no global singleton in game code; docs/concepts/
// ui-shell.md "Bus and logger by context"). It builds an event envelope and
// pushes it onto the injected bus.
//
// The envelope shape and the legal event names are OWNED by the generated
// `event-envelope` contract (Row 7). We derive both from it so they can never
// drift:
//   - the runtime envelope is the contract minus its schema-stamp fields
//     (`version`/`changelog`), which describe how the SCHEMA FILE evolves, not
//     each ephemeral runtime event (docs/concepts/telemetry.md fixes the
//     envelope at the 8 fields below);
//   - the legal names are the schema's `name` enum, read at runtime so a new
//     catalog entry is accepted the moment the contract adds it.
// An unregistered name is REFUSED (thrown) - a Game cannot invent an event the
// catalog does not know.

import eventEnvelopeSchema from "../contracts/event-envelope.schema.json";
import type { EventEnvelope as EventEnvelopeContract } from "../contracts/event-envelope";

import type { EventBus } from "./bus";

/** The runtime envelope: the persisted contract minus its schema-stamp fields. */
export type EventEnvelope = Omit<EventEnvelopeContract, "version" | "changelog">;
/** A legal event name from the generated catalog (compile-time union). */
export type EventName = EventEnvelopeContract["name"];
/** A severity level from the generated contract. */
export type EventLevel = EventEnvelopeContract["level"];

type EventContext = Record<string, unknown>;
type EventData = Record<string, unknown>;

/** The runtime envelope marker version (telemetry.md `v`); bumped if the shape changes. */
const ENVELOPE_V = 1;

// The legal names, read once from the generated schema (single source of truth).
const REGISTERED_EVENT_NAMES: ReadonlySet<string> = new Set(
  eventEnvelopeSchema.properties.name.enum as readonly string[],
);

/** Whether a name is in the generated `event-envelope` catalog. */
export function isRegisteredEventName(name: string): name is EventName {
  return REGISTERED_EVENT_NAMES.has(name);
}

export interface EmitOptions {
  level?: EventLevel;
  ctx?: EventContext;
  data?: EventData;
}

export interface Logger {
  /**
   * Emit one catalog event. Throws if `name` is not in the generated
   * `event-envelope` catalog (a Game cannot invent an event).
   */
  emit(name: EventName, opts?: EmitOptions): void;
  /**
   * A child logger with a new `src` and merged base context, sharing this
   * logger's bus and session. The SessionRunner hands each Game a child scoped
   * to its `gameId` so every Game event carries the session context for free.
   */
  child(src: string, baseCtx?: EventContext): Logger;
}

export interface CreateLoggerOptions {
  bus: EventBus;
  /** The subsystem name stamped as `src` (a Game, a Mode, the runner). */
  src: string;
  /** The play-session id every event on this logger belongs to. */
  session: string;
  /** Injectable clock (epoch ms) for deterministic tests. */
  now?: () => number;
  /** Context merged into every event this logger (and its children) emits. */
  baseCtx?: EventContext;
}

export function createLogger(options: CreateLoggerOptions): Logger {
  const { bus, src, session } = options;
  const now = options.now ?? (() => Date.now());
  const baseCtx = options.baseCtx ?? {};

  return {
    emit(name, opts = {}) {
      if (!isRegisteredEventName(name)) {
        throw new Error(
          `logger: refusing unregistered event name "${name}" - not in the event-envelope catalog`,
        );
      }
      const env: EventEnvelope = {
        ts: now(),
        src,
        v: ENVELOPE_V,
        session,
        name,
        level: opts.level ?? "info",
        ctx: { ...baseCtx, ...(opts.ctx ?? {}) },
        data: opts.data ?? {},
      };
      bus.emit(env);
    },
    child(childSrc, childCtx) {
      return createLogger({
        bus,
        src: childSrc,
        session,
        now,
        baseCtx: { ...baseCtx, ...(childCtx ?? {}) },
      });
    },
  };
}

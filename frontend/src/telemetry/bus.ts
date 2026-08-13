// The structured event bus - the single async transport every runtime
// subsystem shares (CLAUDE.md section 1a: subsystems communicate through
// structured-payload events, never direct calls). A Game emits `puzzle.*`
// through its injected logger; the SessionRunner subscribes here and advances.
// The bus itself knows nothing about who emits or who listens.
//
// Sinks are ordinary subscribers: a bounded ring buffer (always on, cheap) and
// - in development only - a console sink. There is NO network sink (Holy Law
// #1, docs/concepts/telemetry.md); a captured buffer is dumped on demand via
// window.__yt_dump() (wired in runtime.ts).

import type { EventEnvelope, EventLevel } from "./logger";

/** A bus subscriber. Handler errors are isolated so one sink cannot break emit. */
export type EventHandler = (env: EventEnvelope) => void;

export interface EventBus {
  /** Fan an envelope out to every current subscriber (synchronously, isolated). */
  emit(env: EventEnvelope): void;
  /** Subscribe to every envelope; returns an unsubscribe function. */
  subscribe(handler: EventHandler): () => void;
}

export function createEventBus(): EventBus {
  const handlers = new Set<EventHandler>();
  return {
    emit(env) {
      // Snapshot so a handler that (un)subscribes during dispatch is safe, and
      // isolate throws so a faulty sink never breaks the emitter.
      for (const handler of [...handlers]) {
        try {
          handler(env);
        } catch {
          /* a sink/handler must not break emit or sibling handlers */
        }
      }
    },
    subscribe(handler) {
      handlers.add(handler);
      return () => {
        handlers.delete(handler);
      };
    },
  };
}

/** A bounded newest-wins ring buffer of recent events, for on-demand dumps. */
export interface RingBuffer {
  push(env: EventEnvelope): void;
  dump(): EventEnvelope[];
}

export function createRingBuffer(size = 500): RingBuffer {
  const buffer: EventEnvelope[] = [];
  return {
    push(env) {
      buffer.push(env);
      if (buffer.length > size) buffer.shift();
    },
    dump() {
      return buffer.slice();
    },
  };
}

/**
 * Attach the development console sink: each envelope is JSON-stringified to the
 * matching console level. This is the ONE sanctioned console write in the app
 * (eslint no-console is otherwise an error); game and mode code emit through the
 * logger, never console directly.
 */
export function attachConsoleSink(bus: EventBus): () => void {
  return bus.subscribe((env) => {
    const line = JSON.stringify(env);
    const method: EventLevel = env.level;
    // eslint-disable-next-line no-console -- sanctioned structured logger sink (Row 11)
    (console[method] ?? console.log)(line);
  });
}

// The runtime telemetry factory - wires a bus, its sinks, and a root logger
// into one object the app (or a test) creates once and injects via context.
// There are NO module-level singletons here (docs/concepts/ui-shell.md): a test
// spins up an isolated Runtime, and the app creates exactly one at boot.

import {
  attachConsoleSink,
  createEventBus,
  createRingBuffer,
  type EventBus,
} from "./bus";
import { createLogger, type EventEnvelope, type Logger } from "./logger";

export interface Runtime {
  /** The shared event transport (subsystems subscribe here). */
  bus: EventBus;
  /** The root logger (src defaults to "app"); Games get scoped children. */
  logger: Logger;
  /** A snapshot of the recent-events ring buffer (prod debugging). */
  dump(): EventEnvelope[];
}

export interface CreateRuntimeOptions {
  /** Attach the console sink. Defaults to Vite's DEV flag. */
  dev?: boolean;
  /** Stable session id; a random one is minted when omitted. */
  session?: string;
  /** Root `src`. */
  src?: string;
  /** Ring-buffer capacity. */
  ringSize?: number;
  /** Injectable clock (epoch ms). */
  now?: () => number;
}

function makeSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

export function createRuntime(options: CreateRuntimeOptions = {}): Runtime {
  const bus = createEventBus();

  // The ring buffer is always on (bounded, cheap) so window.__yt_dump() works
  // in production; the console sink is development-only.
  const ring = createRingBuffer(options.ringSize);
  bus.subscribe((env) => ring.push(env));

  const dev = options.dev ?? import.meta.env?.DEV === true;
  if (dev) attachConsoleSink(bus);

  const session = options.session ?? makeSessionId();
  const logger = createLogger({
    bus,
    src: options.src ?? "app",
    session,
    ...(options.now ? { now: options.now } : {}),
  });

  const dump = (): EventEnvelope[] => ring.dump();

  // Prod debugging hook: never sent anywhere, dumped on demand (Holy Law #1).
  if (typeof window !== "undefined") {
    (window as unknown as { __yt_dump?: () => EventEnvelope[] }).__yt_dump = dump;
  }

  return { bus, logger, dump };
}

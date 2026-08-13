import { describe, expect, test } from "vitest";

import { createEventBus } from "./bus";
import {
  createLogger,
  isRegisteredEventName,
  type EventEnvelope,
  type EventName,
} from "./logger";

function capture() {
  const bus = createEventBus();
  const events: EventEnvelope[] = [];
  bus.subscribe((env) => events.push(env));
  const logger = createLogger({ bus, src: "test", session: "sess-1", now: () => 1000 });
  return { bus, events, logger };
}

describe("logger + bus", () => {
  test("builds a well-formed runtime envelope for a catalog event", () => {
    const { events, logger } = capture();
    logger.emit("puzzle.completed", { ctx: { gameId: "anagram" }, data: { score: 3 } });

    expect(events).toHaveLength(1);
    const env = events[0]!;
    expect(env).toMatchObject({
      ts: 1000,
      src: "test",
      v: 1,
      session: "sess-1",
      name: "puzzle.completed",
      level: "info",
      ctx: { gameId: "anagram" },
      data: { score: 3 },
    });
  });

  test("the runtime envelope carries only the 8 telemetry fields (no schema stamp)", () => {
    // Decision (Fowler): version/changelog describe how the SCHEMA FILE evolves;
    // they are not duplicated onto every ephemeral runtime event.
    const { events, logger } = capture();
    logger.emit("puzzle.started");
    expect(Object.keys(events[0]!).sort()).toEqual([
      "ctx",
      "data",
      "level",
      "name",
      "session",
      "src",
      "ts",
      "v",
    ]);
  });

  test("refuses an unregistered event name", () => {
    const { logger } = capture();
    expect(() => logger.emit("puzzle.exploded" as EventName)).toThrow(/unregistered event name/i);
  });

  test("accepts every name in the generated catalog", () => {
    const { logger } = capture();
    const names: EventName[] = [
      "puzzle.started",
      "puzzle.attempt.submitted",
      "puzzle.hint.used",
      "puzzle.completed",
      "puzzle.abandoned",
      "mode.session.started",
      "mode.session.completed",
      "streak.updated",
    ];
    for (const name of names) expect(() => logger.emit(name)).not.toThrow();
  });

  test("isRegisteredEventName mirrors the catalog", () => {
    expect(isRegisteredEventName("mode.session.started")).toBe(true);
    expect(isRegisteredEventName("nope")).toBe(false);
  });

  test("a child logger merges src + base context and shares the bus", () => {
    const { events, logger } = capture();
    const child = logger.child("anagram", { modeId: "daily", sessionId: "run-1" });
    child.emit("puzzle.started", { ctx: { itemIndex: 0 } });

    const env = events[0]!;
    expect(env.src).toBe("anagram");
    expect(env.ctx).toMatchObject({ modeId: "daily", sessionId: "run-1", itemIndex: 0 });
  });
});

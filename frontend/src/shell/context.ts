// Runtime injection through Svelte context (docs/concepts/ui-shell.md "Bus and
// logger by context"): the shell puts the structured logger into context so any
// descendant chrome can record events without a console.log or a global
// singleton. Game code receives its logger through GameContext instead, so a
// Game never reaches for context either.

import { getContext, setContext } from "svelte";

import type { Logger } from "../telemetry/logger";

const LOGGER_KEY = Symbol("yt.logger");

/** Provide the logger to descendant components (called by SessionShell). */
export function setLoggerContext(logger: Logger): void {
  setContext(LOGGER_KEY, logger);
}

/** Read the injected logger; throws if used outside a SessionShell. */
export function getLogger(): Logger {
  const logger = getContext<Logger | undefined>(LOGGER_KEY);
  if (logger === undefined) {
    throw new Error("getLogger: no logger in context - render inside a SessionShell");
  }
  return logger;
}

import { describe, expect, test } from "vitest";

import { APP_CONFIG, copyText, isModeEnabled } from "../lib/config";
import { MODE_CARDS } from "./modes";

// The Home is entirely driven by config: which cards are live comes from
// app-config, and every word on them comes from copy.json. These tests are the
// drift gate for both - a card whose copy slug is missing would silently render
// its own slug to a player, and a Mode enabled in config with no card would
// simply never appear.

describe("the Home's Mode catalog", () => {
  test("every catalog card has real copy for every slug it asks for", () => {
    for (const card of MODE_CARDS) {
      for (const slug of [card.titleSlug, card.titleEnSlug, card.noteSlug]) {
        expect(copyText(slug), `${card.modeId} -> ${slug}`).not.toBe(slug);
        expect(copyText(slug).length).toBeGreaterThan(0);
      }
    }
  });

  test("the chrome strings the Home and the session screens use exist", () => {
    for (const slug of [
      "home-tagline",
      "home-modes-label",
      "mode-coming-soon",
      "action-play",
      "action-home",
      "action-settings",
      "daily-loading",
      "daily-empty-title",
      "daily-empty-body",
      "daily-older-day",
      "summary-title",
      "summary-score",
      "summary-solved",
      "summary-streak",
    ]) {
      expect(copyText(slug), slug).not.toBe(slug);
    }
  });

  test("every Mode enabled in config has a card to enable", () => {
    const known = new Set(MODE_CARDS.map((card) => card.modeId));
    for (const modeId of APP_CONFIG.ui.enabledModes) {
      expect(known.has(modeId), `${modeId} is enabled but has no Home card`).toBe(true);
    }
    expect(known.has(APP_CONFIG.ui.defaultMode)).toBe(true);
  });

  test("daily is the live Mode and the rest are honestly marked as coming", () => {
    expect(isModeEnabled("daily")).toBe(true);
    const locked = MODE_CARDS.filter((card) => !isModeEnabled(card.modeId));
    expect(locked.length).toBe(MODE_CARDS.length - APP_CONFIG.ui.enabledModes.length);
  });

  test("a missing slug renders itself rather than a blank control", () => {
    expect(copyText("no-such-slug")).toBe("no-such-slug");
  });
});

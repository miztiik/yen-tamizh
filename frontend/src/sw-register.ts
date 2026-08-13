import { registerSW } from "virtual:pwa-register";

// Registers the app-shell service worker (Row 4). registerType is "autoUpdate":
// a new build's worker installs in the background and applies on the next load,
// so no update prompt interrupts play (Jony: defaults are the product; remove
// before adding). Lifecycle signals are re-broadcast as window CustomEvents - a
// serializable payload on the window per the event-bus rule (CLAUDE.md 1a) - so
// later chrome can react without this module owning any UI or a console sink
// (the logger is the only sanctioned console, Row 11; eslint bans console here).
// In dev the virtual module is a no-op (workbox devOptions are disabled), so
// this is safe to call unconditionally.
export function registerServiceWorker(): void {
  registerSW({
    immediate: true,
    onOfflineReady() {
      window.dispatchEvent(new CustomEvent("pwa:offline-ready"));
    },
    onRegisteredSW(swScriptUrl) {
      window.dispatchEvent(new CustomEvent("pwa:registered", { detail: { swScriptUrl } }));
    },
    onRegisterError(error) {
      window.dispatchEvent(
        new CustomEvent("pwa:register-error", { detail: { message: String(error) } }),
      );
    },
  });
}

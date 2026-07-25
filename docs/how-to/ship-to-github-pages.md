# How To Ship To GitHub Pages

**Last Updated**: 2026-06-28

Use this runbook when changing routing, deployment, PWA metadata, service-worker behaviour, or URLs that need to work under the GitHub Pages project base path.

## Base Path Rules

Production runs under the repository project path. Local dev and preview usually run at `/`.

- Vite `base` is controlled by `GH_PAGES_BASE` in deploy builds.
- Runtime navigation must use `import.meta.env.BASE_URL` or a base-aware asset/path helper.
- Do not navigate to a literal `/` from in-app buttons; that leaves the project page on GitHub Pages.
- Persisted paths, logs, manifests, and docs use relative POSIX paths.

## SPA Fallback

The app uses path routing with a GitHub Pages `404.html` fallback. The production `dist/404.html` must match `dist/index.html` so deep links boot the SPA.

GitHub Pages may return HTTP 404 status with the fallback body. For smoke checks, inspect the body as well as the status.

## PWA Manifest

The PWA manifest is a static file. `start_url`, `scope`, and icon paths stay relative so installed launches work under the project base path.

Do not make manifest URLs root-absolute unless the app stops being a GitHub Pages project page.

## Service Worker

The service worker precaches the shell and opened-game chunks. Theme motif art is not part of the precache budget by default; non-default themes are runtime assets.

Service-worker changes require browser smoke in a production-like build because dev-server behaviour does not prove the install/update contract.

## Validation

1. Run the relevant build and tests.
2. Inspect `dist/index.html` and `dist/404.html` when fallback behaviour changes.
3. Check that generated asset URLs include the expected base in production builds.
4. Smoke a deep route and the installed-app start URL when manifest or service-worker behaviour changes.

## See also

- [../architecture/runtime/stack-and-bundle.md](../architecture/runtime/stack-and-bundle.md) - the runtime stack, PWA/offline contract, and base-path handling this runbook deploys (where the routing and service-worker rationale lives).
- [../concepts/ui-shell.md](../concepts/ui-shell.md) - the screens and routing the SPA fallback serves.

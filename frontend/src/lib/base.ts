// Base-aware path helper. Production runs under the GitHub Pages project base
// (import.meta.env.BASE_URL === "/yen-tamizh/"); local dev and preview run at
// "/". Route in-app navigation and same-origin asset/data URLs through here so
// a path resolves correctly under any base. The base-path contract lives in
// docs/how-to/ship-to-github-pages.md.
export function withBase(path: string, base: string = import.meta.env.BASE_URL): string {
  const trimmedBase = base.endsWith("/") ? base.slice(0, -1) : base;
  const trimmedPath = path.startsWith("/") ? path.slice(1) : path;
  return trimmedPath ? `${trimmedBase}/${trimmedPath}` : `${trimmedBase}/`;
}

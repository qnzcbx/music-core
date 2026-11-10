/** Product defaults come from /api/providers, never from a bundled platform list. */
export const SOURCE_PREFERENCES_KEY = "media-lab.search.sources.v1";
export interface SelectableSource {
  id: string;
  enabled: boolean;
  order?: number;
  primary?: boolean;
  defaultEnabled?: boolean;
  experimental?: boolean;
  capabilities: { search: boolean };
}
export function orderedSources<T extends SelectableSource>(providers: readonly T[]): T[] {
  return [...providers].sort(
    (a, b) =>
      (Number.isFinite(a.order) ? a.order! : Number.MAX_SAFE_INTEGER) -
      (Number.isFinite(b.order) ? b.order! : Number.MAX_SAFE_INTEGER),
  );
}
export function primarySources<T extends SelectableSource>(providers: readonly T[]): T[] {
  // Older catalogs lacking primary flags retain their supplied order, not a client-side product ranking.
  const declared = providers.some((p) => typeof p.primary === "boolean");
  return orderedSources(providers).filter(
    (p) => p.capabilities.search && (declared ? p.primary : !p.experimental),
  );
}
export function sourcePreferenceOrder(
  sources: readonly string[],
  providers: readonly SelectableSource[] = [],
): string[] {
  const unique = [...new Set(sources)];
  const known = [...new Set(orderedSources(providers).map((p) => p.id))];
  return [
    ...known.filter((id) => unique.includes(id)),
    ...unique.filter((id) => !known.includes(id)),
  ];
}
export function validSourcePreferences(
  providers: readonly SelectableSource[],
  sources: unknown,
): string[] {
  const available = new Set(
    providers.filter((p) => p.enabled && p.capabilities.search).map((p) => p.id),
  );
  return Array.isArray(sources)
    ? [
        ...new Set(
          sources.filter((id): id is string => typeof id === "string" && available.has(id)),
        ),
      ]
    : [];
}
export function initialSourcePreferences(
  providers: readonly SelectableSource[],
  raw: string | null,
): string[] {
  let saved: unknown;
  try {
    if (raw && raw.length <= 10000) {
      const parsed: unknown = JSON.parse(raw);
      saved = Array.isArray(parsed)
        ? parsed
        : parsed &&
            typeof parsed === "object" &&
            "schemaVersion" in parsed &&
            parsed.schemaVersion === 1 &&
            "sources" in parsed
          ? parsed.sources
          : undefined;
    }
  } catch {
    /* Invalid preference is not a source permission. */
  }
  const chosen = validSourcePreferences(providers, saved);
  if (chosen.length) return chosen;
  const defaults = validSourcePreferences(
    providers,
    orderedSources(providers)
      .filter((p) => p.defaultEnabled)
      .map((p) => p.id),
  );
  return defaults.length
    ? defaults
    : primarySources(providers)
        .filter((p) => p.enabled)
        .map((p) => p.id)
        .slice(0, 1);
}

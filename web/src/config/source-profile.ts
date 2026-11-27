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

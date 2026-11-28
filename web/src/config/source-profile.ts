import type { ProviderInfo } from '../types/core';

export function orderedSources(providers: readonly ProviderInfo[]): ProviderInfo[] {
  return [...providers].sort((a, b) => a.order - b.order);
}

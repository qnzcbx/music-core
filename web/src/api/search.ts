import type { ProviderId, ProviderInfo, SearchPage } from '../types/core';
import { isDesktop } from '../platform/desktop';
import { requestJson } from './http';
import { invokeCore } from './transport';

export const getProviders = () => isDesktop
  ? invokeCore<ProviderInfo[]>({ op: 'providersList' }, { timeoutMs: 20_000 })
  : requestJson<ProviderInfo[]>('/api/providers');

export function searchSource(providerId: ProviderId, query: string, cursor: string | null, signal: AbortSignal) {
  const payload = { providerId, query, limit: 15, cursor };
  return isDesktop
    ? invokeCore<SearchPage>({ op: 'searchPage', payload }, { signal, timeoutMs: 20_000 })
    : requestJson<SearchPage>('/api/search', { method: 'POST', body: JSON.stringify(payload), signal });
}

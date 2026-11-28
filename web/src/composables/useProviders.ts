import { readonly, ref } from 'vue';
import { getProviders } from '../api/search';
import { orderedSources } from '../config/source-profile';
import type { ProviderInfo } from '../types/core';

const catalog = ref<ProviderInfo[]>([]);
const error = ref('');
let pending: Promise<void> | undefined;

export function providerFor(source: string) {
  return catalog.value.find((provider) => provider.id === source);
}

export function providerName(source: string) {
  return providerFor(source)?.name ?? source;
}

export function useProviders() {
  async function load() {
    if (catalog.value.length) return;
    if (pending) return pending;
    pending = getProviders()
      .then((rows) => {
        catalog.value = orderedSources(rows);
        error.value = '';
      })
      .catch((reason) => {
        error.value = reason instanceof Error ? reason.message : '来源目录加载失败';
        throw reason;
      })
      .finally(() => {
        pending = undefined;
      });
    return pending;
  }

  return { providers: readonly(catalog), providerError: readonly(error), load };
}

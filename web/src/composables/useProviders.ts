import { readonly, ref } from "vue";
import { requestJson } from "../api/http";
import { orderedSources } from "../config/source-profile";
export interface Provider {
  id: string;
  name: string;
  order: number;
  common: boolean;
  primary?: boolean;
  enabled: boolean;
  defaultEnabled: boolean;
  experimental: boolean;
  reason: string;
  capabilities: {
    search: boolean;
    resolve: boolean;
    lyrics: boolean;
    download: boolean;
    qualityPolicy: boolean;
    cover: boolean;
  };
}
const catalog = ref<Provider[]>([]);
const error = ref("");
let pending: Promise<void> | undefined;
export function providerFor(source: string) {
  return catalog.value.find((p) => p.id === source);
}
export function providerName(source: string) {
  return providerFor(source)?.name ?? source;
}
export function useProviders() {
  async function load() {
    if (catalog.value.length) return;
    if (pending) return pending;
    pending = requestJson<Provider[]>("/api/providers", {
      errorMessage: "来源目录加载失败，请重试",
    })
      .then((rows) => {
        catalog.value = orderedSources(rows.map(row=>({...row,enabled:true,primary:true,defaultEnabled:(row as unknown as {defaultSelected:boolean}).defaultSelected})));
        error.value = "";
      })
      .catch((reason) => {
        error.value = reason instanceof Error ? reason.message : "来源目录加载失败";
        throw reason;
      })
      .finally(() => {
        pending = undefined;
      });
    return pending;
  }
  return { providers: readonly(catalog), providerError: readonly(error), load };
}

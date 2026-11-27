<script setup lang="ts">
import type { ProviderInfo } from "../types/core";
import { computed } from "vue";

const sources = defineModel<string[]>("sources", { required: true });
const props = defineProps<{
  providers: readonly ProviderInfo[];
}>();
const primary = computed(() => props.providers.filter((provider) => provider.capabilities?.search));
</script>

<template>
  <div class="source-options">
    <fieldset class="primary-sources" aria-label="主要音乐来源">
      <legend class="sr-only">音乐来源</legend>
      <label 
        v-for="provider in primary" 
        :key="provider.id" 
      >
        <input
          v-model="sources"
          type="checkbox"
          :disabled="sources.length === 1 && sources.includes(provider.id)"
          :value="provider.id"
        />
        <span>
          {{ provider.name }}
        </span>
      </label>
    </fieldset>
  </div>
</template>

<style scoped>
.source-options {
  min-width: 0;
  font-size: 12px;
  color: var(--app-text-muted);
}
fieldset {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}
label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 8px;
  border-radius: 7px;
  white-space: nowrap;
  cursor: pointer;
}
label:has(input:checked) {
  color: var(--app-link);
  background: var(--app-selected);
}
label:hover {
  background: var(--app-hover);
}
label:has(input:focus-visible) {
  outline: 2px solid var(--app-focus);
  outline-offset: 1px;
}
input {
  margin: 0;
  width: 14px;
  height: 14px;
  accent-color: var(--app-accent);
}
small {
  font-size: 10px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
</style>

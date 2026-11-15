<script setup lang="ts">
import GlobalSearch from '../../../components/search/GlobalSearch.vue';
import SearchBar from '../../../components/SearchBar.vue';
import { useCoreClient } from '../../../composables/useCoreClient';
const emit = defineEmits<{
  draftChange: [text: string];
  inputReady: [element: HTMLInputElement | null];
}>();
const {
  searchState: { sources, providers, providerError, loadProviders },
} = useCoreClient();
</script>
<template>
  <div class="home-search">
    <GlobalSearch
      hero
      @draft-change="emit('draftChange', $event)"
      @input-ready="emit('inputReady', $event)"
    />
    <SearchBar
      v-model:sources="sources"
      :providers="providers"
    />
    <p
      v-if="providerError"
      class="home-source-error"
      role="status"
    >
      {{ providerError }} <button @click="loadProviders">重新加载</button>
    </p>
  </div>
</template>
<style scoped>
.home-search {
  width: 100%;
}
.home-search :deep(.source-options) {
  margin-top: 16px;
}
.home-search :deep(.primary-sources) {
  justify-content: center;
  gap: 5px 8px;
}
.home-search :deep(.primary-sources label) {
  min-height: 36px;
}
.home-source-error {
  color: var(--app-danger);
  font-size: 12px;
  line-height: 1.6;
}
.home-source-error button {
  border: 0;
  border-bottom: 1px solid currentColor;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
</style>

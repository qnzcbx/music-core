<script setup lang="ts">
import SearchBar from "../SearchBar.vue";
import { useCoreClient } from "../../composables/useCoreClient";

const {
  searchState: { sources, providers },
} = useCoreClient();
</script>

<template>
  <div class="source-selector">
    <SearchBar v-model:sources="sources" :providers="providers" />
  </div>
</template>

<style scoped>
.source-selector {
  min-width: 0;
}
.source-selector :deep(.primary-sources) {
  flex-wrap: wrap;
}
</style>

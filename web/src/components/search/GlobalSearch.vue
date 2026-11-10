<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import SearchIcon from "~icons/lucide/search";
import XIcon from "~icons/lucide/x";
import { routeSearchQuery } from "../../app/router/search-route";
import { useCoreClient } from "../../composables/useCoreClient";
const { searchState } = useCoreClient();
defineProps<{ hero?: boolean }>();
const composing = ref(false);
const route = useRoute(),
  router = useRouter();
const draft = ref(routeSearchQuery(route.query.q));
watch(
  () => route.fullPath,
  () => {
    draft.value = routeSearchQuery(route.query.q);
  },
);
function submit() {
  if (composing.value) return;
  const q = draft.value.trim();
  if (!q) return;
  draft.value = q;
  if (route.path !== "/search" || routeSearchQuery(route.query.q) !== q)
    void router.push({ path: "/search", query: { q } });
  else void searchState.search();
}
</script>
<template>
  <form
    class="global-search"
    :class="{ 'search-hero': hero }"
    role="search"
    @submit.prevent="submit"
  >
    <label for="query" class="sr-only">搜索曲目</label>
    <input
      id="query"
      v-model="draft"
      type="search"
      maxlength="80"
      autocomplete="off"
      placeholder="搜索歌名或歌手"
      @compositionstart="composing = true"
      @compositionend="composing = false"
      @keydown.enter="
        (event) => {
          if (event.isComposing || composing || event.keyCode === 229) event.preventDefault();
        }
      "
      @keydown.esc.stop="($event.target as HTMLInputElement).blur()"
    />
    <button
      v-if="draft"
      type="button"
      class="clear-btn"
      aria-label="清空输入"
      title="清空"
      @click="draft = ''"
    >
      <XIcon aria-hidden="true" />
    </button>
    <button 
      type="submit" 
      :disabled="!draft.trim()" 
      aria-label="搜索" 
      title="搜索"
    >
      <SearchIcon aria-hidden="true" />
    </button>
  </form>
</template>
<style scoped>
.global-search {
  display: flex;
  align-items: center;
  width: min(100%, 480px);
  min-width: 0;
  height: 42px;
  border: 1px solid var(--app-border-soft);
  border-radius: 12px;
  background: var(--app-input);
  transition:
    border-color 0.18s,
    box-shadow 0.18s;
}
input[type="search"]::-webkit-search-cancel-button {
  -webkit-appearance: none;
  display: none;
}
.global-search:focus-within {
  border-color: var(--app-accent);
  box-shadow: 0 0 0 3px var(--app-focus-ring);
}
.global-search.search-hero {
  width: 100%;
  height: 62px;
  background: color-mix(in srgb, var(--app-surface-raised) 35%, transparent);
  border-color: var(--app-border);
  border-radius: 18px;
  box-shadow: 0 3px 14px var(--app-shadow-soft);
}
.search-hero input {
  padding-left: 22px;
  font-size: 15px;
}
.search-hero button {
  width: 44px;
  height: 44px;
  margin-right: 8px;
  border-radius: 12px;
  color: var(--app-text);
}
.search-hero:focus-within {
  border-color: var(--app-focus);
  box-shadow: 0 0 0 3px var(--app-focus-ring);
}
input {
  width: 100%;
  min-width: 0;
  height: 100%;
  padding: 0 16px;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--app-text);
  font: inherit;
  font-size: 13px;
}
input::placeholder {
  color: var(--app-text-soft);
}
button {
  display: grid;
  place-items: center;
  width: 42px;
  height: 36px;
  flex-shrink: 0;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
}
button:hover:not(:disabled) {
  background: var(--app-hover);
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
svg {
  width: 19px;
  height: 19px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
@media (prefers-reduced-motion: reduce) {
  .global-search {
    transition: none;
  }
}
</style>

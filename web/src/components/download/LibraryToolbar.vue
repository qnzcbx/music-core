<script setup lang="ts">
import { nextTick, ref } from 'vue';
import PlayIcon from '~icons/lucide/play';
import SearchIcon from '~icons/lucide/search';

defineProps<{ canPlay: boolean; canSearch: boolean }>();
defineEmits<{ play: [] }>();
const query = defineModel<string>({ required: true });
const searching = ref(false);
const searchInput = ref<HTMLInputElement>();
const searchButton = ref<HTMLButtonElement>();

async function toggleSearch() {
  searching.value = !searching.value;
  if (!searching.value) query.value = '';
  await nextTick();
  (searching.value ? searchInput.value : searchButton.value)?.focus();
}
</script>

<template>
  <div class="library-toolbar">
    <div class="library-toolbar-actions">
      <button class="library-toolbar-action" type="button" :disabled="!canPlay" @click="$emit('play')">
        <PlayIcon aria-hidden="true" /> 播放全部
      </button>
      <slot />
    </div>
    <div v-if="canSearch" class="library-search">
      <input v-if="searching" ref="searchInput" v-model="query" type="search"
        aria-label="按歌名或歌手搜索" placeholder="搜索歌名或歌手" @keydown.esc.prevent.stop="toggleSearch" />
      <button ref="searchButton" class="library-search-toggle" type="button"
        :aria-expanded="searching" :aria-label="searching ? '关闭歌曲搜索' : '搜索歌曲'"
        :title="searching ? '关闭歌曲搜索' : '搜索歌曲'" @click="toggleSearch">
        <SearchIcon aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.library-toolbar, .library-toolbar-actions, .library-search {
  display: flex;
  align-items: center;
  gap: 8px;
}
.library-toolbar {
  flex-wrap: wrap;
  justify-content: space-between;
  margin-bottom: 12px;
}
.library-toolbar-actions { flex-wrap: wrap; }
.library-toolbar :deep(.library-toolbar-action), .library-search-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--app-border-soft);
  border-radius: 7px;
  background: var(--app-surface);
  color: var(--app-text);
  font-size: 13px;
}
.library-toolbar :deep(.library-toolbar-action:hover:not(:disabled)), .library-search-toggle:hover {
  background: var(--app-hover);
}
.library-toolbar :deep(.library-toolbar-action:active:not(:disabled)), .library-search-toggle:active {
  background: var(--app-selected);
}
.library-toolbar :deep(.library-toolbar-action:disabled) { opacity: .45; cursor: default; }
.library-toolbar :deep(.library-toolbar-action svg) { width: 14px; height: 14px; }
.library-search { max-width: 100%; margin-inline-start: auto; gap: 6px; }
.library-search input {
  width: 190px;
  min-width: 0;
  height: 32px;
  padding-inline: 9px;
  border: 1px solid var(--app-border-soft);
  border-radius: 7px;
  background: var(--app-surface);
  color: var(--app-text);
  font-size: 13px;
}
.library-search-toggle { width: 32px; padding: 0; flex: 0 0 32px; }
.library-search-toggle svg { width: 16px; height: 16px; }
</style>

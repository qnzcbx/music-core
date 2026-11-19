<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import {
  DropdownMenuRoot,
  DropdownMenuTrigger,
  DropdownMenuPortal,
  DropdownMenuContent,
  DropdownMenuItem,
} from 'reka-ui';
import CirclePlusIcon from '~icons/lucide/circle-plus';
import SearchIcon from '~icons/lucide/search';
import XIcon from '~icons/lucide/x';
import { requestJson } from '../../api/http';
import { useCoreClient } from '../../composables/useCoreClient';

import DesktopSongList, { type DesktopSong } from './DesktopSongList.vue';

const props = defineProps<{ tab: 'local' | 'files' }>();
type Library = {
  songs: DesktopSong[];
  downloads: DesktopSong[];
  directories: { id: string; path: string; available: boolean }[];
};

const { downloads, coverRevision } = useCoreClient();
const library = ref<Library>({ songs: [], downloads: [], directories: [] });
const scanDialog = ref<HTMLDialogElement>();
const scanOpen = ref(false);
const searching = ref(false);
const query = ref('');
const searchInput = ref<HTMLInputElement>();
const searchButton = ref<HTMLButtonElement>();
const songs = computed(() =>
  props.tab === 'local' ? library.value.songs : library.value.downloads,
);
const visibleSongs = computed(() => {
  const search = query.value.trim().toLowerCase();
  if (props.tab !== 'local' || !search) return songs.value;
  return songs.value.filter((song) =>
    [song.title, song.artist].some((value) => value.toLowerCase().includes(search)),
  );
});
const empty = computed(() => loaded.value && !songs.value.length);
const busy = ref(false);
const loaded = ref(false);
const error = ref('');
let refreshPending = false;

async function openScan() {
  error.value = '';
  await nextTick();
  scanDialog.value?.showModal();
  scanOpen.value = true;
}

async function toggleSearch() {
  searching.value = !searching.value;
  if (!searching.value) query.value = '';
  await nextTick();
  if (searching.value) searchInput.value?.focus();
  else searchButton.value?.focus();
}

async function refresh(action?: 'files' | 'choose' | 'refresh' | 'remove', id?: string) {
  if (busy.value) {
    if (!action) refreshPending = true;
    return;
  }
  busy.value = true;
  error.value = '';
  try {
    library.value = await requestJson<Library>(
      '/api/local-library',
      action
        ? {
            method: 'POST',
            body: JSON.stringify({ action, id }),
            timeoutMs: 600_000,
          }
        : {},
    );
    loaded.value = true;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取本地歌曲';
    // 刷新失败后重新读取保存的快照，更新目录可用性。
    if (action === 'refresh') {
      library.value = await requestJson<Library>('/api/local-library').catch(() => library.value);
    }
  } finally {
    busy.value = false;
    if (refreshPending) {
      refreshPending = false;
      void refresh();
    }
  }
}

onMounted(() => void refresh());
watch([downloads.saved, coverRevision], () => void refresh());
watch(
  () => props.tab,
  () => {
    scanOpen.value = false;
    searching.value = false;
    query.value = '';
  },
);
</script>

<template>
  <section :aria-label="tab === 'local' ? '本地歌曲' : '下载歌曲'">
    <p
      v-if="error && !scanOpen"
      role="alert"
    >
      {{ error }}
    </p>
    <template v-if="tab === 'local'">
      <div :class="empty ? 'local-empty' : 'local-toolbar'">
        <template v-if="empty">
          <h2>还没有本地歌曲</h2>
          <p>添加歌曲或文件夹，拾音下载的音乐也会出现在这里。</p>
        </template>
        <div class="local-toolbar-row">
          <div class="local-controls">
            <DropdownMenuRoot>
              <DropdownMenuTrigger as-child>
                <button
                  class="add-trigger"
                  type="button"
                  :disabled="busy"
                >
                  <CirclePlusIcon aria-hidden="true" /> 添加音乐
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuPortal>
                <DropdownMenuContent
                  class="music-layer add-menu"
                  align="start"
                  :side-offset="6"
                >
                  <DropdownMenuItem
                    data-slot="dropdown-menu-item"
                    @select="refresh('files')"
                  >
                    手动添加
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    data-slot="dropdown-menu-item"
                    @select="openScan"
                  >
                    自动扫描
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenuPortal>
            </DropdownMenuRoot>
          </div>
          <div
            v-if="loaded && !empty"
            class="local-search"
          >
            <input
              v-if="searching"
              ref="searchInput"
              v-model="query"
              type="search"
              aria-label="按歌名或歌手搜索本地歌曲"
              placeholder="搜索歌名或歌手"
              @keydown.esc.prevent="toggleSearch"
            />
            <button
              ref="searchButton"
              class="local-search-toggle"
              type="button"
              :aria-expanded="searching"
              :aria-label="searching ? '关闭本地歌曲搜索' : '搜索本地歌曲'"
              :title="searching ? '关闭本地歌曲搜索' : '搜索本地歌曲'"
              @click="toggleSearch"
            >
              <SearchIcon aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
      <dialog
        ref="scanDialog"
        class="scan-dialog"
        aria-labelledby="scan-title"
        @close="scanOpen = false"
        @cancel="busy && $event.preventDefault()"
      >
        <header class="scan-header">
          <h2 id="scan-title">自动扫描添加</h2>
          <button
            type="button"
            class="scan-close"
            aria-label="关闭"
            :disabled="busy"
            @click="scanDialog?.close()"
          >
            <XIcon aria-hidden="true" />
          </button>
        </header>
        <div class="scan-body">
          <div class="scan-toolbar">
            <p>选择要扫描的音乐文件夹</p>
            <button
              type="button"
              :disabled="busy"
              @click="refresh('choose')"
            >
              添加文件夹
            </button>
          </div>
          <p
            v-if="error"
            role="alert"
          >
            {{ error }}
          </p>
          <div
            class="scan-folders"
            :aria-busy="busy"
          >
            <p
              v-if="!library.directories.length"
              class="scan-empty"
            >
              还没有添加文件夹
            </p>
            <div
              v-for="directory in library.directories"
              :key="directory.id"
              class="directory-row"
            >
              <div class="directory-path">
                <span>{{ directory.path }}</span>
                <small v-if="!directory.available">目录暂不可用</small>
              </div>
              <div class="local-controls">
                <button
                  type="button"
                  :disabled="busy"
                  @click="refresh('refresh', directory.id)"
                >
                  重新扫描
                </button>
                <button
                  type="button"
                  :disabled="busy"
                  @click="refresh('remove', directory.id)"
                >
                  移除
                </button>
              </div>
            </div>
          </div>
          <dl class="scan-rules">
            <dt>扫描范围</dt>
            <dd>所选文件夹及其子文件夹</dd>
            <dt>文件格式</dt>
            <dd>MP3、FLAC</dd>
          </dl>
          <footer class="scan-footer">
            <button
              type="button"
              :disabled="busy"
              @click="scanDialog?.close()"
            >
              完成
            </button>
          </footer>
        </div>
      </dialog>
    </template>
    <p
      v-else-if="empty"
      class="local-empty"
    >
      还没有下载的歌曲
    </p>
    <p
      v-if="searching && query.trim() && !visibleSongs.length"
      class="local-empty"
      role="status"
    >
      没有找到匹配的本地歌曲
    </p>
    <DesktopSongList
      :songs="visibleSongs"
      @removed="refresh()"
    />
  </section>
</template>

<style scoped>
.local-toolbar {
  padding: 0 0 12px;
}
.local-empty {
  min-height: 44vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  color: var(--app-text-muted);
}
.local-empty h2 {
  font-size: 18px;
  font-weight: 500;
  color: var(--app-text);
  margin: 0;
}
.local-empty p {
  font-size: 13px;
  margin: 0;
}
.local-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.local-toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.local-search {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  margin-inline-start: auto;
}
.local-search input {
  box-sizing: border-box;
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
.local-search-toggle {
  display: grid;
  place-items: center;
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  padding: 0;
}
.local-search-toggle svg {
  width: 16px;
  height: 16px;
}
.add-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.add-trigger svg {
  width: 14px;
  height: 14px;
}
.music-layer.add-menu {
  padding: 4px;
  border-radius: 8px;
  min-width: 112px;
}
.add-menu [data-slot='dropdown-menu-item'] {
  font-size: 13px;
  line-height: 1.4;
  padding: 6px 10px;
  border-radius: 5px;
}
.scan-dialog {
  width: min(620px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
  box-sizing: border-box;
  padding: 0;
  border: 1px solid var(--app-border-soft);
  border-radius: 12px;
  background: var(--app-surface-raised);
  color: var(--app-text);
}
.scan-dialog::backdrop {
  background: #0006;
}
.scan-header,
.scan-toolbar,
.scan-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.scan-header {
  padding: 13px 18px;
  border-bottom: 1px solid var(--app-border-soft);
}
.scan-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}
.scan-close {
  display: grid;
  place-items: center;
  padding: 5px;
  border-color: transparent;
  background: transparent;
}
.scan-close svg {
  width: 16px;
  height: 16px;
}
.scan-body {
  padding: 16px 18px;
  font-size: 13px;
}
.scan-toolbar p {
  margin: 0;
}
.scan-folders {
  min-height: 140px;
  max-height: min(260px, 32dvh);
  overflow: auto;
  margin-top: 10px;
  padding: 0 12px;
  border-radius: 6px;
  background: var(--app-surface-subtle);
}
.scan-empty {
  padding: 36px 0;
  text-align: center;
  color: var(--app-text-muted);
}
.directory-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--app-border-soft);
  overflow-wrap: anywhere;
  font-size: 13px;
}
.directory-path {
  flex: 1 1 220px;
  min-width: 0;
}
.directory-row small {
  display: block;
  color: var(--app-text-muted);
}
.scan-rules {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 5px 12px;
  margin: 14px 0;
}
.scan-rules dt {
  color: var(--app-text-muted);
}
.scan-rules dd {
  margin: 0;
}
.scan-footer {
  justify-content: flex-end;
}
.scan-footer button {
  background: var(--app-selected);
  min-width: 72px;
}
button {
  border: 1px solid var(--app-border-soft);
  border-radius: 7px;
  padding: 7px 11px;
  background: var(--app-surface);
  color: inherit;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}
button:hover,
button[aria-expanded='true'] {
  background: var(--app-hover);
}
</style>

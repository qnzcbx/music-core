<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { requestJson } from '../../api/http';
import { useCoreClient } from '../../composables/useCoreClient';

type Song = {
  id: string;
  path: string;
  title: string;
  artist: string;
  format: string;
  available: boolean;
};
type Library = {
  songs: Song[];
  directories: { id: string; path: string; available: boolean }[];
};

const { downloads, player } = useCoreClient();
const library = ref<Library>({ songs: [], directories: [] });
const adding = ref(false);
const busy = ref(false);
const loaded = ref(false);
const error = ref('');
let refreshPending = false;

async function refresh(action?: 'files' | 'choose' | 'refresh' | 'remove', id?: string) {
  if (busy.value) {
    if (!action) refreshPending = true;
    return;
  }
  busy.value = true;
  error.value = '';
  try {
    library.value = await requestJson<Library>('/api/local-library', action ? {
      method: 'POST', body: JSON.stringify({ action, id }), timeoutMs: 600_000,
    } : {});
    loaded.value = true;
    if (action === 'files' || action === 'choose') adding.value = false;
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

function current(song: Song) {
  return player.selectedId.value === JSON.stringify(['local', song.id]);
}

function play(song: Song) {
  if (current(song)) void player.toggle();
  else void player.selectDesktopLocal(song);
}

onMounted(() => void refresh());
watch(downloads.saved, () => void refresh());
defineExpose({ refresh: () => refresh() });
</script>

<template>
  <section class="local-library" aria-label="本地歌曲">
    <div :class="['local-actions', { empty: loaded && !library.songs.length }]">
      <p v-if="loaded && !library.songs.length">还没有本地歌曲</p>
      <button :disabled="busy" :aria-expanded="adding" @click="adding = !adding">添加音乐</button>
      <div v-if="adding" class="local-buttons">
        <button :disabled="busy" @click="refresh('files')">添加歌曲</button>
        <button :disabled="busy" @click="refresh('choose')">添加文件夹</button>
      </div>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <details v-if="library.directories.length">
      <summary>已添加的目录</summary>
      <div v-for="directory in library.directories" :key="directory.id" class="local-row">
        <div>
          <div>{{ directory.path }}</div>
          <small v-if="!directory.available">目录暂不可用</small>
        </div>
        <div class="local-buttons">
          <button :disabled="busy" @click="refresh('refresh', directory.id)">刷新</button>
          <button :disabled="busy" @click="refresh('remove', directory.id)">移除</button>
        </div>
      </div>
    </details>
    <div v-for="song in library.songs" :key="song.id" class="local-row" :data-local-id="song.id">
      <div>
        <strong>{{ song.title }}</strong>
        <small v-if="song.artist">{{ song.artist }}</small>
        <small :title="song.path">{{ song.format.toUpperCase() }} · {{ song.path }}</small>
      </div>
      <span v-if="!song.available">文件不可用</span>
      <button v-else :disabled="current(song) && player.busy.value" @click="play(song)">
        {{ current(song) && player.playing.value ? '暂停' : '播放' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.local-actions { margin: 16px 0; }
.local-actions.empty { text-align: center; padding: 48px 0; }
.local-buttons { display: inline-flex; flex-wrap: wrap; gap: 8px; margin: 4px; }
.local-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--app-border-soft); overflow-wrap: anywhere; }
.local-row small { display: block; color: var(--app-text-muted); }
button { border: 1px solid var(--app-border-soft); border-radius: 8px; padding: 8px 12px; background: var(--app-hover); color: inherit; cursor: pointer; white-space: nowrap; }
summary { cursor: pointer; }
</style>

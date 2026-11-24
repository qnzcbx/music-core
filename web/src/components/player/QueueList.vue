<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue';
import { isDesktop } from '../../api/transport';
import { MAX_QUEUE } from '../../player/player-persistence';
import { requestJson } from '../../api/http';
import { useCoreClient } from '../../composables/useCoreClient';
import PlayIcon from '~icons/lucide/play';
import PauseIcon from '~icons/lucide/pause';
import LoadingIcon from '~icons/lucide/loader-circle';
import DownloadStateIcon from '../DownloadStateIcon.vue';
import type { QueueEntry } from '../../types/music';
import CoverArt from '../CoverArt.vue';
import TrashIcon from '~icons/lucide/trash-2';
import OrderIcon from '~icons/lucide/list-ordered';
import RepeatIcon from '~icons/lucide/repeat';
import RepeatOneIcon from '~icons/lucide/repeat-1';
import ShuffleIcon from '~icons/lucide/shuffle';

const { player, downloads, coverRevision } = useCoreClient();
const { entries, current, navigation } = player.queue;
// 运行时的 URL 仅用于展示，绝不并入持久化的队列元数据。
const cachedCovers = shallowRef(new Map<string, string>());

if (isDesktop) {
  watch(
    [() => entries.value.slice(0, MAX_QUEUE), coverRevision],
    async ([batch], _, onCleanup) => {
      let current = true;
      onCleanup(() => {
        current = false;
      });
      if (!batch.length) {
        cachedCovers.value = new Map();
        return;
      }
      try {
        const urls = await requestJson<(string | null)[]>('/api/media-cache/queue-covers', {
          method: 'POST',
          body: JSON.stringify({
            entries: batch.map((row) =>
              'kind' in row ? { fileId: row.fileId } : { track: row.track },
            ),
          }),
        });
        if (current)
          cachedCovers.value = new Map(
            batch.flatMap((row, index) => {
              const url = urls[index];
              return url ? [[row.key, url] as const] : [];
            }),
          );
      } catch {
        if (current) cachedCovers.value = new Map();
      }
    },
    { immediate: true },
  );
}
const modes = [
  { id: 'order', label: '顺序播放', icon: OrderIcon },
  { id: 'repeat_all', label: '列表循环', icon: RepeatIcon },
  { id: 'repeat_one', label: '单曲循环', icon: RepeatOneIcon },
  { id: 'shuffle', label: '随机播放', icon: ShuffleIcon },
] as const;
const mode = computed(() => modes.find((m) => m.id === navigation.mode)!);
function cycle() {
  player.queue.setMode(
    modes[(modes.findIndex((m) => m.id === navigation.mode) + 1) % modes.length]!.id,
  );
}
function downloadEntry(entry: QueueEntry) {
  downloads.choose({
    identity: entry.track,
    id: entry.key,
    source: entry.track.providerId,
    platformId: entry.track.platformId,
    mid: entry.track.platformId,
    name: entry.metadata.title,
    title: entry.metadata.title,
    artist: entry.metadata.artist,
    album: entry.metadata.album,
    cover: entry.metadata.cover,
    duration: entry.metadata.durationSeconds,
    resolveState: 'idle',
  });
}
</script>

<template>
  <div class="queue-body">
    <header class="queue-header">
      <div>
        <h2>播放队列</h2>
        <span>{{ entries.length }} 首歌曲</span>
      </div>
      <div class="queue-actions">
        <button
          :title="mode.label"
          :aria-label="`当前${mode.label}，切换播放模式`"
          @click="cycle"
        >
          <component :is="mode.icon" />
        </button>
        <button
          title="清空队列"
          aria-label="清空队列"
          :disabled="!entries.length"
          @click="player.queue.clear"
        >
          <TrashIcon />
        </button>
      </div>
    </header>

    <div
      class="queue-content"
      data-reka-swipe-ignore
      tabindex="0"
      aria-label="队列歌曲列表"
    >
      <p
        v-if="!entries.length"
        class="queue-empty"
      >
        空空如也
      </p>
      <div
        v-else
        class="queue-list"
      >
        <article
          v-for="entry in entries"
          :key="entry.key"
          :data-current="entry.key === current"
          :data-queue-key="entry.key"
        >
          <div class="queue-cover">
            <CoverArt
              clover-fallback
              :src="cachedCovers.get(entry.key) ?? entry.metadata.cover"
            />
            <span
              class="queue-cover-play"
              :data-icon="
                entry.key === player.selectedId.value && player.playing.value ? 'pause' : 'play'
              "
              aria-hidden="true"
            >
              <LoadingIcon
                v-if="
                  entry.key === player.selectedId.value &&
                  ['opening', 'positioning'].includes(player.phase.value)
                "
                class="row-loading"
              />
              <PauseIcon
                v-else-if="entry.key === player.selectedId.value && player.playing.value"
              />
              <PlayIcon v-else />
            </span>
          </div>
          <button
            class="queue-choose"
            :disabled="entry.key === current && player.busy.value"
            :title="entry.key === current ? player.actionLabel.value : '播放'"
            :aria-current="entry.key === current ? 'true' : undefined"
            @click="
              entry.key === current && player.selected.value
                ? player.toggle()
                : player.queue.choose(entry)
            "
          >
            <span class="sr-only">
              {{ entry.key === player.selectedId.value ? player.actionLabel.value : '播放' }}
              {{ entry.metadata.title }}
            </span>
            <strong aria-hidden="true">{{ entry.metadata.title }}</strong>
            <small aria-hidden="true">{{ entry.metadata.artist }}</small>
          </button>
          <button
            v-if="!('kind' in entry)"
            class="queue-download"
            :aria-label="`下载 ${entry.metadata.title}`"
            @click.stop="downloadEntry(entry)"
          >
            <DownloadStateIcon :identity="entry.track" />
          </button>
          <button
            class="queue-remove"
            :aria-label="`移除 ${entry.metadata.title}`"
            @click.stop="player.queue.remove(entry.key)"
          >
            ×
          </button>
        </article>
      </div>
    </div>
  </div>
</template>

<style scoped>
.queue-list article {
  position: relative;
  isolation: isolate;
  padding: 10px 8px;
  transition: background-color 0.12s;
}
.queue-list article:hover,
.queue-list article:focus-within {
  background: var(--app-hover, var(--app-selected));
}
.queue-list article[data-current='true'] {
  background: var(--app-selected);
}
.queue-cover {
  position: relative;
  pointer-events: none;
}
.queue-cover-play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: #17352d70;
  color: white;
  opacity: 0;
  transition: opacity 0.12s;
}
.queue-cover-play svg {
  width: 20px;
  height: 20px;
}
.queue-list article:hover .queue-cover-play,
.queue-list article:focus-within .queue-cover-play,
.queue-list article[data-current='true'] .queue-cover-play {
  opacity: 1;
}
.queue-choose::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
}
.music-layer .queue-choose {
  padding: 0;
  border-radius: 0;
  background: transparent;
}
.music-layer .queue-choose:hover {
  background: transparent;
}
.queue-choose:focus-visible {
  outline: none;
}
.queue-choose:focus-visible::before {
  outline: 2px solid var(--app-focus);
  outline-offset: -2px;
}
.queue-remove {
  position: relative;
  z-index: 2;
  margin-left: auto;
  flex-shrink: 0;
}
.row-loading {
  animation: queue-loading 1s linear infinite;
}
@keyframes queue-loading {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .queue-list article,
  .queue-cover-play {
    transition: none;
  }
  .row-loading {
    animation: none;
  }
}
</style>

<style scoped>
.queue-download {
  position: relative;
  z-index: 2;
  flex-shrink: 0;
}
.queue-download :deep(svg) {
  width: 18px;
  height: 18px;
}
</style>

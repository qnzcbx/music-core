<script setup lang="ts">
import { computed } from 'vue';
import { useCoreClient } from '../composables/useCoreClient';
const { player, downloads } = useCoreClient();
import PauseIcon from '~icons/lucide/pause';
import LoadingIcon from '~icons/lucide/loader-circle';
import PlayIcon from '~icons/lucide/play';
import DownloadStateIcon from './DownloadStateIcon.vue';
import MoreIcon from '~icons/lucide/ellipsis';
import PlayNextButton from './player/PlayNextButton.vue';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from './ui/dropdown-menu';
import CoverArt from './CoverArt.vue';
import { providerName, providerFor } from '../composables/useProviders';
import type { SearchEntry as Song } from '../types/music';
import { downloadBlockReason } from '../utils/track-access';
import { queueKey } from '../utils/player-queue';

const props = defineProps<{
  song: Song;
  selected: boolean;
  version?: boolean;
  groupExpanded?: boolean;
}>();
const emit = defineEmits<{
  play: [song: Song];
}>();

const source = computed(() => providerName(props.song.identity.providerId));
const versionLabel = computed(() => props.song.title + ' · ' + source.value);
const downloadUnsupported = computed(
  () => providerFor(props.song.identity.providerId)?.capabilities?.download === false,
);
const durationText = computed(() =>
  typeof props.song.duration === 'number' && Number.isFinite(props.song.duration)
    ? Math.floor(props.song.duration / 60) +
      ':' +
      String(Math.floor(props.song.duration % 60)).padStart(2, '0')
    : props.song.duration || '—',
);
const album = computed(() =>
  props.song.album && props.song.album !== 'NULL' ? props.song.album : '—',
);
const downloadKey = computed(() => queueKey(props.song.identity));
function download() {
  void downloads.choose(props.song);
}
</script>

<template>
  <article
    class="song-row"
    :class="{ selected, 'version-row': version }"
    :data-song-id="song.id"
    :data-provider="song.identity.providerId"
    :data-platform-id="song.identity.platformId"
  >
    <button
      :title="selected ? player.actionLabel.value : '播放此版本'"
      :disabled="selected && player.busy.value"
      type="button"
      class="row-play action-play"
      :aria-label="(selected ? player.actionLabel.value : '试听') + ' ' + versionLabel"
      @click.stop="selected ? player.toggle() : emit('play', song)"
    />
    <div class="row-identity">
      <div class="cover">
        <CoverArt
          clover-fallback
          :src="song.cover"
          loading="lazy"
        />
        <span
          class="cover-play"
          :data-icon="
            selected && ['opening', 'positioning'].includes(player.phase.value)
              ? 'loading'
              : selected && player.playing.value
                ? 'pause'
                : 'play'
          "
          aria-hidden="true"
        >
          <LoadingIcon
            v-if="selected && ['opening', 'positioning'].includes(player.phase.value)"
            class="row-loading"
          />
          <PauseIcon v-else-if="selected && player.playing.value" />
          <PlayIcon v-else />
        </span>
      </div>
      <div class="song">
        <h3>{{ song.title }}</h3>
        <div class="song-subline">
          <span class="row-artist">{{ song.artist }}</span>
          <span class="row-source">{{ source }}</span>
          <span
            v-if="groupExpanded"
            class="version-badge"
            >当前主版本</span
          >
        </div>
        <small class="mobile-metadata">{{ album }} · {{ durationText }}</small>
      </div>
    </div>

    <div
      class="song-actions"
      aria-label="版本操作"
    >
      <PlayNextButton :song="song" class="song-action action-play-next" />
      <button
        :disabled="
          !!downloadBlockReason(song) ||
          downloadUnsupported ||
          downloads.pending.value.has(downloadKey)
        "
        :title="downloadBlockReason(song) || '下载此版本'"
        type="button"
        class="song-action action-download"
        :aria-label="'下载 ' + versionLabel"
        @click.stop="download"
      >
        <DownloadStateIcon :identity="song.identity" />
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button
            title="更多"
            type="button"
            class="song-action action-more"
            :aria-label="'更多 ' + versionLabel"
            @click.stop
          >
            <MoreIcon aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          class="music-layer"
          align="end"
        >
          <DropdownMenuItem
            class="mode-option"
            @select="selected ? player.toggle() : emit('play', song)"
          >
            立即播放
          </DropdownMenuItem>
          <DropdownMenuItem
            class="mode-option"
            @select="player.queue.add(song)"
          >
            添加到播放队列
          </DropdownMenuItem>
          <DropdownMenuItem
            class="mode-option"
            :disabled="!player.queue.entries.value.some((e) => e.key === player.queue.key(song))"
            @select="player.queue.remove(player.queue.key(song))"
          >
            从队列移除
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <span class="row-album">{{ album }}</span>
    <time class="row-duration">{{ durationText }}</time>
    <div class="row-versions"><slot /></div>
  </article>
</template>

<style scoped>
.song-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(220px, 2fr) 116px minmax(130px, 1fr) 64px 104px;
  align-items: center;
  gap: 12px;
  min-width: 0;
  min-height: 76px;
  padding: 12px 10px;
  margin: 0;
  border-bottom: 1px solid var(--app-border-soft);
  border-radius: 0;
}
.song-row:hover,
.song-row:focus-within {
  background: var(--app-hover);
}
.song-row.selected {
  background: var(--app-selected);
}
.row-play {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  border: 0;
  border-radius: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;
}
.row-play:disabled {
  cursor: default;
}
.row-play:focus-visible {
  outline: 2px solid var(--app-focus);
  outline-offset: -2px;
}
.row-identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  pointer-events: none;
}
.cover {
  position: relative;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 5px;
}
.cover-play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  opacity: 0;
  background: #17352d70;
  color: #fff;
  border-radius: 5px;
  transition: opacity 0.12s;
}
.cover-play svg {
  width: 20px;
  height: 20px;
}
.song-row:hover .cover-play,
.song-row:focus-within .cover-play,
.song-row.selected .cover-play {
  opacity: 1;
}
.song {
  min-width: 0;
  flex: 1;
}
.download-feedback {
  display: block;
  font-size: 11px;
  color: var(--app-text-muted);
  margin: 4px 0;
}
.song h3 {
  margin: 0 0 5px;
  font-size: 14px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.song-subline {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  min-width: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--app-text-muted);
}
.row-artist {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-source {
  font-size: 10px;
  color: var(--app-text-muted);
}
.resource-state,
.version-badge {
  font-size: 10px;
  color: var(--app-text-muted);
}
.row-album {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--app-text-muted);
  pointer-events: none;
}
.row-duration {
  font:
    11px Consolas,
    monospace;
  color: var(--app-text-muted);
  pointer-events: none;
}
.row-versions {
  position: relative;
  z-index: 2;
  min-width: 0;
}
.song-actions {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.12s;
}
.song-row:hover .song-actions,
.song-row:focus-within .song-actions {
  opacity: 1;
}
.song-action {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--app-link);
  cursor: pointer;
}
.song-action :deep(svg) {
  width: 18px;
  height: 18px;
}
.song-action:hover:not(:disabled) {
  background: var(--app-surface-raised);
}
.song-action:disabled {
  opacity: 0.4;
  cursor: default;
}
.mobile-metadata {
  display: none;
}
.song-row :deep(.download-status) {
  position: relative;
  z-index: 2;
  grid-column: 1/-1;
  width: 100%;
  padding: 0 0 0 58px;
  font-size: 11px;
}
@media (max-width: 1050px) {
  .song-row {
    grid-template-columns: minmax(0, 1fr) 116px 104px;
    gap: 10px;
  }
  .row-album,
  .row-duration {
    display: none;
  }
  .mobile-metadata {
    display: block;
    color: var(--app-text-muted);
    font-size: 10px;
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
@media (max-width: 600px) {
  .mobile-metadata {
    display: none;
  }
  .song-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
    padding: 10px 4px;
    min-height: 72px;
  }
  .row-identity {
    gap: 10px;
  }
  .song-actions {
    grid-column: 2;
    grid-row: 1;
    opacity: 1;
    gap: 0;
  }
  .song-action {
    width: 36px;
    height: 40px;
  }
  .row-versions {
    grid-column: 1/-1;
    justify-self: end;
  }
  .row-versions:empty {
    display: none;
  }
  .song-row :deep(.download-status) {
    padding-left: 0;
  }
  .song-subline {
    gap: 2px 6px;
  }
}
@media (hover: none) {
  .song-actions {
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .cover-play,
  .song-actions {
    transition: none;
  }
}
</style>

<style scoped>
.row-loading {
  animation: row-loading 1s linear infinite;
}
@keyframes row-loading {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .row-loading {
    animation: none;
  }
}
</style>

<style scoped>
.song-actions:has(
  [data-download-state]:not([data-download-state='none']):not([data-download-state='cancelled'])
) {
  opacity: 1;
}
@media (min-width: 601px) and (hover: hover) {
  .song-row:not(:hover):not(:focus-within)
    .song-actions:has(
      [data-download-state]:not([data-download-state='none']):not([data-download-state='cancelled'])
    )
    :is(.action-play-next, .action-more) {
    opacity: 0;
  }
}
</style>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { isDesktop } from '../api/transport';
import { desktopLyrics } from '../composables/useDesktopLyrics';
import { useCoreClient } from '../composables/useCoreClient';
import { usePlayerVisuals } from '../composables/usePlayerTransition';
import { useMediaQuery } from '@vueuse/core';
import DownloadStateIcon from './DownloadStateIcon.vue';
import { isLocalSong } from '../types/music';
import { trackIdentity } from '../utils/player-queue';
import { downloadBlockReason } from '../utils/track-access';
import ExpandIcon from '~icons/lucide/expand';
import BackIcon from '~icons/lucide/shrink';
import PlayerLayoutSelector from './PlayerLayoutSelector.vue';
import CoverArt from './CoverArt.vue';
import LoadingIcon from '~icons/lucide/loader-circle';
import PlayIcon from '~icons/lucide/play';
import PauseIcon from '~icons/lucide/pause';
import PreviousIcon from '~icons/lucide/skip-back';
import NextIcon from '~icons/lucide/skip-forward';
import PlaybackModeMenu from './player/PlaybackModeMenu.vue';
import VolumePopover from './player/VolumePopover.vue';
import QueuePanel from './player/QueuePanel.vue';
import '../styles/player-layers.css';

const { player, downloads } = useCoreClient();
const props = defineProps<{ immersive?: boolean }>();
const visuals = usePlayerVisuals();
const mobile = useMediaQuery('(max-width:600px)');
const compactMini = computed(() => !props.immersive && mobile.value);
const compactImmersive = computed(() => !!props.immersive && mobile.value);
const emit = defineEmits<{ lockChange: [locked: boolean] }>();
const panels: Record<string, boolean> = {};

function panel(name: string, open: boolean) {
  panels[name] = open;
  emit('lockChange', Object.values(panels).some(Boolean));
}
watch(compactImmersive, () => {
  for (const key of ['volume', 'queue']) delete panels[key];
  emit('lockChange', Object.values(panels).some(Boolean));
});
const { selected, time, duration, playing, message, phase } = player;
const host = ref<HTMLElement>(),
  preview = ref<number | null>(null);
onMounted(() => {
  if (!props.immersive && host.value) {
    visuals.setMiniFooter(host.value);
    visuals.setMiniCover(host.value.querySelector('.mini-cover-art'));
  }
});
const downloadable = computed(() =>
  selected.value && !isLocalSong(selected.value) && !downloadBlockReason(selected.value)
    ? selected.value
    : null,
);
const downloadIdentity = computed(() =>
  downloadable.value ? trackIdentity(downloadable.value) : null,
);
const progress = computed(() => preview.value ?? time.value);
const pauseAction = computed(() => !player.failed.value && playing.value);
function transportAction() {
  return player.toggle();
}
const format = (value: number) =>
  `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
function seek(event: Event) {
  player.seek(Number((event.target as HTMLInputElement).value));
  preview.value = null;
}
</script>

<template>
  <footer
    ref="host"
    class="player"
    :class="{ 'immersive-controls': immersive }"
    :data-phase="phase"
  >
    <div
      v-if="!compactImmersive"
      class="player-info"
    >
      <button
        v-if="immersive"
        class="immersive-back"
        aria-label="收起歌曲详情页"
        title="收起歌曲详情页"
        @click="visuals.close"
      >
        <BackIcon />
      </button>
      <button
        v-if="!immersive"
        class="player-cover"
        :disabled="!selected"
        title="打开沉浸式播放器"
        aria-label="打开沉浸式播放器"
        @click="visuals.open"
      >
        <span class="mini-cover-art">
          <CoverArt
            clover-fallback
            :src="selected?.cover"
          />
        </span>
        <span
          v-if="selected"
          class="cover-expand"
          aria-hidden="true"
        >
          <ExpandIcon />
        </span>
      </button>
      <div class="player-meta">
        <span class="track-title">
          {{ selected?.title || selected?.name || '拾音' }}
        </span>
        <span class="player-artist">
          {{ selected?.artist || (selected ? '' : '听我想听') }}
        </span>
        <span class="player-album">{{ selected?.album }}</span>
      </div>
    </div>

    <div
      v-if="!compactMini"
      class="transport"
    >
      <div class="transport-buttons">
        <PlaybackModeMenu
          :immersive="immersive"
          @open-change="panel('mode', $event)"
        />
        <button
          aria-label="上一首"
          :disabled="!player.queue.hasPrevious.value"
          @click="player.queue.previous"
        >
          <PreviousIcon />
        </button>
        <button
          class="play-toggle"
          :disabled="!selected || player.busy.value"
          :aria-label="player.actionLabel.value"
          :title="player.actionLabel.value"
          @click="transportAction"
        >
          <LoadingIcon
            v-if="player.busy.value"
            class="play-loading"
          />
          <PauseIcon v-else-if="pauseAction" />
          <PlayIcon v-else />
        </button>
        <button
          aria-label="下一首"
          :disabled="!player.queue.hasNext.value"
          @click="player.queue.next"
        >
          <NextIcon />
        </button>
        <QueuePanel
          v-if="compactImmersive"
          immersive
          compact
          @open-change="panel('queue', $event)"
        />
        <VolumePopover
          v-else
          :immersive="immersive"
          @open-change="panel('volume', $event)"
        />
      </div>
      <div class="progress-row">
        <time>{{ format(progress) }}</time>
        <input
          aria-label="播放进度"
          type="range"
          min="0"
          :max="duration"
          step="0.1"
          :value="progress"
          :disabled="!selected || duration <= 0"
          @input="preview = Number(($event.target as HTMLInputElement).value)"
          @change="seek"
          @blur="preview = null"
        />
        <time>{{ duration ? format(duration) : '—:—' }}</time>
      </div>
    </div>

    <div
      v-if="!compactImmersive"
      class="player-tools"
    >
      <button
        v-if="!immersive"
        aria-label="下载当前歌曲"
        title="下载当前歌曲"
        :disabled="!downloadable"
        @click="downloadable && downloads.choose(downloadable)"
      >
        <DownloadStateIcon :identity="downloadIdentity" />
      </button>

      <button
        v-if="compactMini"
        class="mini-play-toggle"
        :disabled="!selected || player.busy.value"
        :title="player.actionLabel.value"
        :aria-label="player.actionLabel.value"
        @click="transportAction"
      >
        <LoadingIcon
          v-if="player.busy.value"
          class="play-loading"
        />
        <PauseIcon v-else-if="pauseAction" />
        <PlayIcon v-else />
      </button>
      <button
        v-else
        :disabled="isDesktop ? desktopLyrics.pending.value : !selected"
        :aria-pressed="isDesktop ? desktopLyrics.open.value : undefined"
        :title="
          isDesktop
            ? desktopLyrics.error.value ||
              (desktopLyrics.open.value ? '收起桌面歌词' : '打开桌面歌词')
            : '查看歌词'
        "
        :aria-label="
          isDesktop ? (desktopLyrics.open.value ? '收起桌面歌词' : '打开桌面歌词') : '查看歌词'
        "
        @click="isDesktop ? desktopLyrics.toggle() : visuals.open()"
      >
        词
      </button>
      <QueuePanel
        :compact="compactMini"
        :immersive="immersive"
        @open-change="panel('queue', $event)"
      />
    </div>
    <PlayerLayoutSelector
      v-if="immersive"
      class="immersive-style-entry"
      icon-only
      above
      :layout="visuals.layout.value"
      :alignment="visuals.lyricAlignment.value"
      :background="visuals.backgroundMode.value"
      :ring-preset="visuals.ringPreset.value"
      @background="visuals.selectBackground"
      @ring="visuals.selectRingPreset"
      :transitioning="visuals.phase.value === 'layout'"
      @select="visuals.selectLayout"
      @align="visuals.selectLyricAlignment"
      @open-change="panel('style', $event)"
    />
  </footer>
</template>

<style scoped>
.player-meta .playback-status.notice-visible {
  position: static;
  display: block;
  width: auto;
  height: auto;
  clip-path: none;
  font-size: 11px;
  color: var(--app-text-muted);
}
.player {
  z-index: 20;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 1.4fr) minmax(0, 1fr);
  align-items: center;
  gap: 24px;
  border-top-width: 1px;
}
.player :deep(button) {
  cursor: pointer;
  color: var(--mini-text);
  background: transparent;
  border: 0;
}
.player :deep(button):disabled {
  cursor: default;
  opacity: 0.4;
}
.player :deep(button):focus-visible {
  outline: 2px solid var(--mini-accent);
  outline-offset: 3px;
}
.player :deep(svg) {
  width: 19px;
  height: 19px;
}
.player-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.player-cover {
  position: relative;
  padding: 0;
  border-radius: 8px;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  overflow: hidden;
  background: var(--mini-surface);
}
.mini-cover-art {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 8px;
}
.player-meta {
  min-width: 0;
}
.track-title {
  display: block;
  max-width: 100%;
  padding: 0;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  text-align: left;
}
.player-meta :is(.track-title, .player-artist, .player-album) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.player-meta > span {
  display: block;
  color: var(--mini-muted);
  font-size: 11px;
  line-height: 1.6;
}
.player-meta .playback-status {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
.transport {
  min-width: 0;
}
.transport-buttons {
  display: flex;
  justify-content: center;
  gap: 18px;
  align-items: center;
}
.transport-buttons :deep(button),
.player-tools > :deep(button) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  border-radius: 8px;
  min-width: 36px;
  height: 36px;
}
.transport-buttons :deep(button):hover:not(:disabled),
.player-tools > :deep(button):hover:not(:disabled),
.player :deep(button)[aria-expanded='true'] {
  background: color-mix(in srgb, var(--mini-text) 12%, transparent);
}
.transport-buttons .play-toggle {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--mini-button);
  color: var(--mini-button-text);
}
.transport-buttons .play-toggle:hover:not(:disabled) {
  background: var(--mini-button);
  filter: brightness(1.12);
}
.progress-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 6px;
}
.progress-row input {
  min-width: 0;
  flex: 1;
  accent-color: var(--mini-accent);
  height: 16px;
  cursor: pointer;
}
.progress-row time {
  font:
    10px Consolas,
    monospace;
  color: var(--mini-muted);
  min-width: 30px;
}
.progress-row time:last-child {
  text-align: right;
}
.player-tools {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 8px;
}
.player-tools > :deep(button) {
  gap: 5px;
  font: inherit;
  font-size: 14px;
}
.queue-count {
  font-size: 10px;
  color: var(--mini-muted);
}
.player-immersive .mini-cover-art {
  opacity: 0;
}
.mini-collapse {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font:
    30px Georgia,
    serif;
}
.player-immersive {
  background: var(--mini-bg-immersive);
}
@container player-workspace (max-width: 860px) {
  .player {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px 12px;
  }
  .transport {
    grid-column: 1/-1;
    grid-row: 2;
  }
  .player-tools {
    grid-column: 2;
    grid-row: 1;
  }
  .player-cover {
    width: 44px;
    height: 44px;
  }
  .player-album {
    display: none !important;
  }
  .transport-buttons {
    gap: 18px;
  }
}
@media (max-width: 600px) {
  .player {
    gap: 6px 8px;
  }
  .player-info {
    gap: 8px;
  }
  .player-tools {
    gap: 0;
  }
  .player-tools > :deep(button) {
    padding: 6px;
  }
  .transport-buttons :deep(button) {
    min-width: 40px;
    height: 40px;
  }
  .transport-buttons {
    gap: 12px;
  }
}
</style>

<style scoped>
.immersive-controls {
  position: fixed;
  inset: auto 0 0;
  z-index: 25;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 540px) minmax(0, 1fr);
  padding: 14px 28px max(14px, env(safe-area-inset-bottom));
  background: transparent;
  background-image: none;
  border: 0;
  box-shadow: none;
  color: var(--mini-text);
  backdrop-filter: none;
  --mini-text: var(--player-control, #293238);
  --mini-muted: var(--player-text-muted, #515c62);
  --mini-accent: #52646b;
  --mini-button: #d6dcdb;
  --mini-button-text: #263337;
  --mini-surface: #ecece8;
}
.immersive-controls .player-cover,
.immersive-controls .player-album {
  display: none;
}
.immersive-back {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  min-width: 44px;
  height: 44px;
  border-radius: 8px;
}
.immersive-back:hover {
  background: #ffffff70;
}
.immersive-controls :deep(.layout-selector summary) {
  border: 0;
  padding: 8px;
  color: var(--mini-text);
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}
@media (max-width: 760px) {
  .immersive-controls {
    grid-template-columns: minmax(0, 1fr) auto;
    padding: 10px 12px max(10px, env(safe-area-inset-bottom));
  }
  .immersive-controls .player-info {
    grid-column: 1;
    grid-row: 1;
  }
  .immersive-controls .transport {
    grid-column: 1/-1;
    grid-row: 2;
  }
  .immersive-controls .player-tools {
    grid-column: 2;
    grid-row: 1;
  }
}
</style>

<style scoped>
.cover-expand {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  border-radius: inherit;
  background: #18252b80;
  color: #fff;
  opacity: 0;
  transition: opacity 0.12s ease;
}
.player .cover-expand svg {
  width: 24px;
  height: 24px;
}
.player-cover:hover:not(:disabled) .cover-expand,
.player-cover:focus-visible .cover-expand {
  opacity: 1;
}
.player .immersive-back svg {
  width: 24px;
  height: 24px;
}
.immersive-controls::before,
.immersive-controls::after {
  content: none;
  display: none;
}
.immersive-controls :deep(.layout-card) {
  display: block;
  height: auto;
  min-height: 0;
  min-width: 0;
  padding: 6px;
  border: 1px solid transparent;
  color: var(--player-control);
}
.immersive-controls :deep(.layout-card[aria-pressed='true']) {
  border-color: var(--player-focus);
}
@media (prefers-reduced-motion: reduce) {
  .cover-expand {
    transition: none;
  }
}
</style>

<style scoped>
@media (max-width: 600px) {
  .immersive-controls {
    display: block;
    padding: 12px 22px max(20px, env(safe-area-inset-bottom));
    -webkit-tap-highlight-color: transparent;
  }
  .immersive-controls .transport {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .immersive-controls .progress-row {
    order: 0;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
    margin: 0;
  }
  .immersive-controls .progress-row input {
    grid-column: 1/-1;
    grid-row: 1;
    width: 100%;
    height: 22px;
    margin: 0;
  }
  .immersive-controls .progress-row time {
    grid-row: 2;
    line-height: 1.2;
    font-size: 10px;
    opacity: 0.8;
  }
  .immersive-controls .transport-buttons {
    order: 1;
    justify-content: space-between;
    gap: 10px;
    padding: 0 4px;
  }
  .immersive-controls .transport-buttons :deep(button) {
    width: 44px;
    min-width: 44px;
    height: 44px;
    padding: 8px;
  }
  .immersive-controls .transport-buttons :deep(svg) {
    width: 24px;
    height: 24px;
  }
  .immersive-controls .transport-buttons .play-toggle {
    width: 56px;
    min-width: 56px;
    height: 56px;
    border: 1.5px solid var(--mini-text);
    background: transparent;
  }
  .immersive-controls .transport-buttons .play-toggle svg {
    width: 28px;
    height: 28px;
  }
}
</style>

<style scoped>
@media (max-width: 600px) {
  .player:not(.immersive-controls) {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
  }
  .player:not(.immersive-controls) .player-tools {
    grid-column: 2;
    grid-row: 1;
    gap: 4px;
  }
  .player:not(.immersive-controls) .player-tools > :deep(button) {
    width: 44px;
    height: 44px;
    padding: 10px;
  }
  .player:not(.immersive-controls) .player-tools :deep(svg) {
    width: 24px;
    height: 24px;
  }
  .player:not(.immersive-controls) .player-meta .track-title {
    font-size: 13px;
    color: var(--mini-text);
  }
  .player:not(.immersive-controls) .player-album {
    display: none;
  }
}
</style>

<style scoped>
.play-loading {
  animation: play-loading 1s linear infinite;
}
@keyframes play-loading {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .play-loading {
    animation: none;
  }
}
</style>

<style scoped>
.immersive-style-entry {
  position: fixed;
  right: 136px;
  bottom: 28px;
  z-index: 50;
}
@media (max-width: 600px) {
  .immersive-style-entry {
    right: 18px;
    top: 18px;
    bottom: auto;
  }
}
</style>

<style scoped>
.player button[aria-pressed='true'] {
  color: var(--primary, #399985);
  background: color-mix(in srgb, currentColor 12%, transparent);
}
</style>

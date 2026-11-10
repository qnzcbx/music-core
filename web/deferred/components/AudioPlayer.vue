<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import PlayIcon from "~icons/lucide/play";
import PauseIcon from "~icons/lucide/pause";
import PreviousIcon from "~icons/lucide/skip-back";
import NextIcon from "~icons/lucide/skip-forward";
import OrderIcon from "~icons/lucide/list-ordered";
import ShuffleIcon from "~icons/lucide/shuffle";
import RepeatIcon from "~icons/lucide/repeat";
import RepeatOneIcon from "~icons/lucide/repeat-1";
import VolumeIcon from "~icons/lucide/volume-2";
import LowVolumeIcon from "~icons/lucide/volume-1";
import MuteIcon from "~icons/lucide/volume-x";
import QueueIcon from "~icons/lucide/list-music";
import { usePlayerStore } from "../stores/player";
import type { Song, TrackSnapshot } from "../types/music";
import CoverArt from "./CoverArt.vue";
import { usePlayerVisuals } from "../composables/usePlayerTransition";
const { immersive, setMiniCover, setMiniFooter } = usePlayerVisuals();
const props = defineProps<{
  active: Song | null;
  snapshot?: TrackSnapshot;
  playback: string;
  hasPrevious: boolean;
  hasNext: boolean;
  queueOpen: boolean;
  popup: string | null;
  recovering?: boolean;
}>();
const emit = defineEmits<{
  ready: [element: HTMLAudioElement];
  state: [message: string];
  time: [seconds: number];
  openLyrics: [];
  toggleImmersive: [];
  toggle: [];
  seek: [seconds: number];
  previous: [];
  next: [];
  popover: [kind: string, anchor: HTMLElement];
}>();
const player = ref<HTMLAudioElement>();
const { playing, currentTime, duration, volume, queue, navigation } = usePlayerStore();
const preview = ref<number | null>(null);
const progress = computed(() => preview.value ?? currentTime.value);
const title = computed(() => props.active?.name ?? props.snapshot?.title ?? "选择歌曲开始播放");
const artist = computed(
  () => props.active?.artist ?? props.snapshot?.artist ?? "从搜索结果中选择一首歌",
);
const album = computed(() => {
  const value = (props.active?.album ?? props.snapshot?.album ?? "").trim();
  return /^(null|undefined|未知专辑|专辑未知|unknown(?: album)?)$/i.test(value) ? "" : value;
});
const modes = {
  order: { name: "顺序播放", icon: OrderIcon },
  shuffle: { name: "随机播放", icon: ShuffleIcon },
  repeat_all: { name: "列表循环", icon: RepeatIcon },
  repeat_one: { name: "单曲循环", icon: RepeatOneIcon },
};
function timeLabel(value: number) {
  if (!Number.isFinite(value) || value < 0) return "0:00";
  return `${Math.floor(value / 60)}:${Math.floor(value % 60)
    .toString()
    .padStart(2, "0")}`;
}
function commitSeek(event: Event) {
  emit("seek", Number((event.target as HTMLInputElement).value));
  preview.value = null;
}
function open(kind: string, event: MouseEvent) {
  emit("popover", kind, event.currentTarget as HTMLElement);
}
watch(
  () => props.active?.id,
  () => {
    preview.value = null;
  },
);
function reportTime() {
  emit("time", player.value?.currentTime ?? 0);
}
onMounted(() => {
  if (player.value) emit("ready", player.value);
});
</script>
<template>
  <footer :ref="setMiniFooter" class="player" :class="{ 'player-immersive': immersive }">
    <div class="player-info">
      <button
        class="player-cover"
        :disabled="!active"
        :aria-label="immersive ? '收起沉浸式播放器' : '打开沉浸式播放器'"
        :aria-expanded="immersive"
        @click="emit('toggleImmersive')"
      >
        <span :ref="setMiniCover" class="mini-cover-art" data-cover-role="mini"
          ><CoverArt :src="active?.cover ?? snapshot?.cover"
        /></span>
        <span v-if="immersive" class="mini-collapse" aria-hidden="true">♬</span>
      </button>
      <div class="player-meta">
        <button class="track-title" :disabled="!active" :title="title" @click="emit('openLyrics')">
          {{ title }}
        </button>
        <span class="player-artist" :title="artist">{{ artist }}</span>
        <span v-if="album" class="player-album" :title="album">{{ album }}</span>
        <span class="playback-status" role="status">{{ playback }}</span>
      </div>
    </div>
    <div class="transport">
      <div class="transport-buttons">
        <button
          :aria-label="`播放模式：${modes[navigation.mode].name}`"
          :title="modes[navigation.mode].name"
          aria-haspopup="dialog"
          aria-controls="player-mode-popover"
          :aria-expanded="popup === 'mode'"
          @click="open('mode', $event)"
        >
          <component :is="modes[navigation.mode].icon" aria-hidden="true" />
        </button>
        <button aria-label="上一首" :disabled="!hasPrevious" @click="emit('previous')">
          <PreviousIcon aria-hidden="true" />
        </button>
        <button
          class="play-toggle"
          :aria-label="playing ? '暂停' : '播放'"
          :disabled="(!active && !snapshot) || recovering"
          @click="emit('toggle')"
        >
          <PauseIcon v-if="playing" aria-hidden="true" /><PlayIcon v-else aria-hidden="true" />
        </button>
        <button aria-label="下一首" :disabled="!hasNext" @click="emit('next')">
          <NextIcon aria-hidden="true" />
        </button>
        <button
          aria-label="音量设置"
          :title="`音量 ${Math.round(volume * 100)}%`"
          aria-haspopup="dialog"
          aria-controls="player-volume-popover"
          :aria-expanded="popup === 'volume'"
          @click="open('volume', $event)"
        >
          <MuteIcon v-if="volume === 0" aria-hidden="true" /><LowVolumeIcon
            v-else-if="volume < 0.5"
            aria-hidden="true"
          /><VolumeIcon v-else aria-hidden="true" />
        </button>
      </div>
      <div class="progress-row">
        <time>{{ timeLabel(progress) }}</time>
        <input
          aria-label="播放进度"
          type="range"
          min="0"
          :max="duration || 0"
          step="0.1"
          :value="progress"
          :disabled="!active || recovering || duration <= 0"
          @input="preview = Number(($event.target as HTMLInputElement).value)"
          @change="commitSeek"
          @blur="preview = null"
        />
        <time>{{ duration > 0 ? timeLabel(duration) : "—:—" }}</time>
      </div>
    </div>
    <div class="player-tools">
      <button
        :disabled="!active"
        aria-label="歌词"
        title="打开歌词播放器"
        @click="emit('openLyrics')"
      >
        词
      </button>
      <button
        data-queue-entrypoint
        aria-label="播放列表"
        title="播放队列"
        aria-controls="player-queue-popover"
        :aria-expanded="queueOpen"
        @click="open('queue', $event)"
      >
        <QueueIcon aria-hidden="true" /><span class="queue-count">{{ queue.length }}</span>
      </button>
    </div>
    <audio
      ref="player"
      :src="active ? `/api/stream/${active.id}` : undefined"
      hidden
      preload="none"
      @timeupdate="reportTime"
      @seeked="reportTime"
      @emptied="emit('time', 0)"
      @playing="emit('state', '正在播放')"
      @pause="emit('state', '已暂停（浏览器仍可能缓冲）')"
      @seeking="emit('state', '正在跳转…')"
      @error="emit('state', '音频加载或解码失败，请查看 Debug 响应')"
    />
  </footer>
</template>
<style scoped>
.player {
  z-index: 20;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 1.4fr) minmax(0, 1fr);
  align-items: center;
  gap: 24px;
  border-top-width: 1px;
}
.player button {
  cursor: pointer;
  color: var(--mini-text);
  background: transparent;
  border: 0;
}
.player button:disabled {
  cursor: default;
  opacity: 0.4;
}
.player button:focus-visible {
  outline: 2px solid var(--mini-accent);
  outline-offset: 3px;
}
.player svg {
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
.transport-buttons button,
.player-tools button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  border-radius: 8px;
  min-width: 36px;
  height: 36px;
}
.transport-buttons button:hover:not(:disabled),
.player-tools button:hover:not(:disabled),
.player button[aria-expanded="true"] {
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
.player-tools button {
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
  .player-tools button {
    padding: 6px;
  }
  .transport-buttons button {
    min-width: 40px;
    height: 40px;
  }
  .transport-buttons {
    gap: 12px;
  }
}
</style>

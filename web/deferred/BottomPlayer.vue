<script setup lang="ts">
import { computed, ref, shallowRef, watch } from "vue";

import AudioPlayer from "./AudioPlayer.vue";
import { useLabSession } from "../composables/useLabSession";
import type { QueueEntry } from "../types/music";
import { usePlayerVisuals } from "../composables/usePlayerTransition";
import PlayerPopover from "./player/PlayerPopover.vue";
import PlaybackQueuePanel from "./player/PlaybackQueuePanel.vue";
import OrderIcon from "~icons/lucide/list-ordered";
import ShuffleIcon from "~icons/lucide/shuffle";
import RepeatIcon from "~icons/lucide/repeat";
import RepeatOneIcon from "~icons/lucide/repeat-1";
import VolumeIcon from "~icons/lucide/volume-2";
import MuteIcon from "~icons/lucide/volume-x";
import { usePlayerStore } from "../stores/player";
import type { PlaybackMode } from "../player/queue-navigation";

const visuals = usePlayerVisuals();
const {
  audio,
  lease,
  conversions,
  recovery,
  queueController,
  togglePlayback,
  selectSong,
  resolving,
  resolveError,
} = useLabSession();
const {
  navigation,
  hasPrevious,
  hasNext,
  busy: queueBusy,
  message: queueMessage,
} = queueController;
const { state: recoveryState, busy: recovering } = recovery;
const {
  checking: conversionChecking,
  error: conversionError,
  visible: conversionVisible,
} = conversions;
const { state: leaseState, retry: retryLease } = lease;
const {
  active,
  currentEntry,
  playback,
  attachPlayer,
  currentQueueKey,
  restoring: restoringAudio,
} = audio;
const popup = ref<string | null>(null);
const anchor = shallowRef<HTMLElement>();
const queueOpen = computed(() => popup.value === "queue");
const { volume } = usePlayerStore();
let previousVolume = volume.value > 0 ? volume.value : 1;
watch(
  volume,
  (value) => {
    if (value > 0) previousVolume = value;
  },
  { flush: "sync" },
);
function mute() {
  audio.setVolume(volume.value > 0 ? 0 : previousVolume);
}
function closePopup(restore = false) {
  popup.value = null;
  if (restore) anchor.value?.focus({ preventScroll: true });
}
function openPopover(kind: string, element: HTMLElement) {
  if (popup.value === kind) {
    closePopup(true);
    return;
  }
  anchor.value = element;
  popup.value = kind;
}
const modes = [
  { value: "order", label: "顺序播放", icon: OrderIcon },
  { value: "shuffle", label: "随机播放", icon: ShuffleIcon },
  { value: "repeat_all", label: "列表循环", icon: RepeatIcon },
  { value: "repeat_one", label: "单曲循环", icon: RepeatOneIcon },
] as const;
function selectMode(value: PlaybackMode) {
  queueController.setMode(value);
  closePopup(true);
}
function moveMode(event: KeyboardEvent) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const items = Array.from(
    (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>("button"),
  );
  const index = items.indexOf(event.target as HTMLButtonElement);
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? items.length - 1
        : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
  items[next]?.focus();
}
function openLyrics() {
  closePopup();
  if (active.value) visuals.open();
}
function chooseSong(song: QueueEntry) {
  closePopup();
  // 点击当前曲目仅收起队列，避免重新连接媒体和重置 Debug。
  if (
    song.key === currentQueueKey.value &&
    active.value &&
    !navigation.value.upNextKeys.includes(song.key) &&
    !audio.failure.value
  )
    return;
  void selectSong(song);
}
</script>
<template>
  <p v-if="leaseState.message && !recovering" class="lease-notice" role="status">
    {{ leaseState.message }}
    <button v-if="leaseState.canRetry" @click="retryLease">重试会话保护</button>
  </p>
  <p
    v-if="recoveryState.message"
    class="recovery-notice"
    :data-recovery-status="recoveryState.status"
    role="status"
  >
    {{ recoveryState.message }}
    <button
      v-if="recoveryState.canRetry"
      :disabled="recovering || resolving"
      @click="recovery.retry"
    >
      重新解析当前歌曲
    </button>
  </p>
  <p v-if="resolving || resolveError" class="resolve-notice" role="status">
    {{ resolving ? "正在解析播放资源…" : resolveError }}
  </p>
  <p
    v-else-if="queueMessage && !queueOpen"
    class="resolve-notice"
    :class="{
      'play-next-notice': queueMessage.startsWith('已安排') || queueMessage.includes('无需重复'),
    }"
    role="status"
  >
    {{ queueMessage }}
  </p>
  <p v-if="conversionError && !conversionVisible" class="lease-notice" role="status">
    {{ conversionError }}
    <button :disabled="conversionChecking" @click="conversions.retry">重新检测 FLAC</button>
  </p>
  <PlayerPopover
    v-if="popup && anchor"
    :key="popup"
    :anchor="anchor"
    :kind="popup"
    :label="popup === 'mode' ? '选择播放模式' : popup === 'volume' ? '调整音量' : '播放队列面板'"
    @close="closePopup"
  >
    <div
      v-if="popup === 'mode'"
      class="playback-mode-menu"
      role="menu"
      aria-label="播放模式"
      @keydown="moveMode"
    >
      <button
        v-for="mode in modes"
        :key="mode.value"
        role="menuitemradio"
        :aria-checked="navigation.mode === mode.value"
        @click="selectMode(mode.value)"
      >
        <component :is="mode.icon" aria-hidden="true" /><span>{{ mode.label }}</span
        ><span v-if="navigation.mode === mode.value" aria-hidden="true">✓</span>
      </button>
    </div>
    <div v-else-if="popup === 'volume'" class="volume-popover-content">
      <input
        aria-label="音量"
        aria-orientation="vertical"
        type="range"
        min="0"
        max="1"
        step="0.01"
        :value="volume"
        :aria-valuetext="`${Math.round(volume * 100)}%`"
        @input="audio.setVolume(Number(($event.target as HTMLInputElement).value))"
      />
      <output>{{ Math.round(volume * 100) }}%</output>
      <button :aria-label="volume > 0 ? '静音' : '恢复音量'" @click="mute">
        <VolumeIcon v-if="volume > 0" aria-hidden="true" /><MuteIcon v-else aria-hidden="true" />
      </button>
    </div>
    <PlaybackQueuePanel v-else @choose="chooseSong" @close="closePopup(true)" />
  </PlayerPopover>
  <AudioPlayer
    :active="active"
    :snapshot="currentEntry?.metadata"
    :playback="playback"
    :has-previous="hasPrevious && !queueBusy && !resolving && !recovering"
    :has-next="hasNext && !queueBusy && !resolving && !recovering"
    :queue-open="queueOpen"
    :popup="popup"
    :recovering="restoringAudio || resolving || queueBusy"
    @ready="attachPlayer"
    @state="playback = $event"
    @open-lyrics="openLyrics"
    @toggle-immersive="
      closePopup();
      visuals.toggle();
    "
    @toggle="togglePlayback"
    @seek="audio.seek"
    @previous="queueController.previous"
    @next="queueController.next()"
    @popover="openPopover"
  />
</template>
<style scoped>
.playback-mode-menu {
  width: 180px;
  display: grid;
  gap: 3px;
}
.playback-mode-menu button {
  display: flex;
  align-items: center;
  gap: 12px;
  text-align: left;
  padding: 12px;
  font-size: 12px;
}
.playback-mode-menu button span:first-of-type {
  flex: 1;
}
.playback-mode-menu button[aria-checked="true"] {
  color: var(--app-link);
  background: var(--app-hover);
}
.volume-popover-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 14px 10px 6px;
  width: 66px;
}
.volume-popover-content input {
  writing-mode: vertical-lr;
  direction: rtl;
  width: 20px;
  height: 130px;
  accent-color: var(--app-link);
  cursor: pointer;
}
.volume-popover-content output {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.volume-popover-content button {
  display: grid;
  place-items: center;
  width: 40px;
  height: 36px;
}
/* Native vertical range retains keyboard and touch support. */
.resolve-notice.play-next-notice {
  bottom: calc(var(--mini-player-height, 116px) + 14px);
  width: max-content;
  max-width: calc(100vw - 32px);
  padding: 10px 18px;
  font-size: 12px;
  line-height: 1.5;
}
</style>

<style scoped>
.resolve-notice {
  position: fixed;
  bottom: 100px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 40;
  background: var(--app-hover);
  color: var(--app-link);
  padding: 12px 24px;
  border-radius: 12px;
  box-shadow: 0 2px 16px var(--app-shadow-color);
}
.lease-notice {
  position: fixed;
  bottom: 145px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 39;
  width: max-content;
  max-width: calc(100vw - 32px);
  background: var(--app-hover);
  color: var(--app-link);
  padding: 10px 18px;
  border-radius: 10px;
  font-size: 12px;
}
.lease-notice button {
  margin-left: 8px;
  border: 0;
  border-bottom: 1px solid currentColor;
  color: inherit;
  background: transparent;
  cursor: pointer;
}
.recovery-notice {
  position: fixed;
  bottom: 175px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 41;
  max-width: calc(100vw - 32px);
  padding: 10px 18px;
  border-radius: 10px;
  background: var(--app-hover);
  color: var(--app-link);
  font-size: 12px;
  box-shadow: 0 2px 16px var(--app-shadow-color);
}
.recovery-notice button {
  margin-left: 8px;
  border: 0;
  border-bottom: 1px solid currentColor;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
</style>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import Previous from '~icons/lucide/skip-back';
import Next from '~icons/lucide/skip-forward';
import Play from '~icons/lucide/play';
import Pause from '~icons/lucide/pause';
import Chevron from '~icons/lucide/chevron-right';
import Check from '~icons/lucide/check';
import Lock from '~icons/lucide/lock';
import Gear from '~icons/lucide/settings-2';
import Close from '~icons/lucide/x';
import { bridge, lyricChannel } from '../composables/useDesktopLyrics';
import {
  acceptSnapshot,
  lyricSnapshot,
  type PlaybackAction,
  type Update,
} from '../player/desktop-lyrics';

const settingsWindow = new URLSearchParams(location.search).has('settings');
const storageKey = 'musiccore:desktop-lyrics:settings:v1';
const colors = [
  { name: '白色', value: '#ffffff' },
  { name: '暖黄', value: '#ffe095' },
  { name: '薄荷绿', value: '#a9f1d0' },
  { name: '浅蓝', value: '#a9dbff' },
  { name: '桃粉', value: '#ffc3d8' },
];
type Position = [number, number];
type Layout = 'horizontal' | 'vertical';
function readSettings() {
  let raw;
  try {
    raw = JSON.parse(localStorage.getItem(storageKey) ?? '{}') ?? {};
  } catch {
    raw = {};
  }
  const position = (value: unknown): Position | null =>
    Array.isArray(value) &&
    value.length === 2 &&
    value.every((n) => Number.isInteger(n) && Math.abs(n) <= 2147483647)
      ? [value[0], value[1]]
      : null;
  return {
    size: Number.isInteger(raw.size) ? Math.min(42, Math.max(18, raw.size)) : 28,
    color: colors.find((color) => color.value === raw.color)?.value ?? colors[0]!.value,
    layout: (raw.layout === 'vertical' ? 'vertical' : 'horizontal') as Layout,
    double: raw.double === true,
    positions: {
      horizontal: position(raw.positions?.horizontal),
      vertical: position(raw.positions?.vertical),
    },
  };
}
const settings = ref(readSettings());
const vertical = computed(() => settings.value.layout === 'vertical');
const menu = ref(false),
  movingLayout = ref(false);
const update = ref<Update>({ sequence: 0, snapshot: lyricSnapshot(null, null, 0) });
const snapshot = computed(() => update.value.snapshot);
const playback = computed(() => update.value.playback);
const settingsButton = ref<HTMLButtonElement>();
const settingsPanel = ref<HTMLElement>();
const colorMenu = ref(false);
watch(menu, (open) => {
  if (!open) colorMenu.value = false;
});
function play(action: PlaybackAction) {
  channel.postMessage({ type: 'playback', action });
}
function dismissMenu() {
  if (settingsWindow)
    void bridge?.core.invoke('desktop_lyrics_settings_window', { show: false }).catch(() => {});
  else if (menu.value) toggleMenu();
}
let toggling = false;
async function toggleMenu() {
  const anchor = settingsButton.value?.getBoundingClientRect();
  if (!anchor || !bridge || toggling) return;
  toggling = true;
  try {
    await bridge.core.invoke('toggle_desktop_lyrics_settings', {
      anchorX: anchor.left,
      anchorY: anchor.bottom,
    });
  } catch {
    /* 即使弹窗失败，也保证歌词窗口仍然可用。 */
  } finally {
    toggling = false;
  }
}
const channel = new BroadcastChannel(lyricChannel);
let ready: (() => void) | undefined;
channel.onmessage = ({ data }) => {
  if (data?.snapshot) {
    update.value = acceptSnapshot(update.value, data);
    ready?.();
  }
};
let alive = true;
const unlisteners: (() => void)[] = [];
function save() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(settings.value));
  } catch {
    /* 保留会话设置 */
  }
}
function font(delta: number) {
  settings.value.size = Math.min(42, Math.max(18, settings.value.size + delta));
  save();
}
function color(value: string) {
  settings.value.color = value;
  save();
}
async function place(layout: Layout, double: boolean) {
  if (movingLayout.value || !bridge) return;
  movingLayout.value = true;
  try {
    const pos = await bridge.core.invoke<Position>('place_desktop_lyrics', {
      vertical: layout === 'vertical',
      double,
      saved: settings.value.positions[layout],
    });
    Object.assign(settings.value, { layout, double });
    settings.value.positions[layout] = pos;
    save();
  } finally {
    movingLayout.value = false;
  }
}
function change(layout: Layout, double: boolean) {
  Object.assign(settings.value, { layout, double });
  save();
  dismissMenu();
}
function syncSettings(event: StorageEvent) {
  if (event.key !== storageKey) return;
  const next = readSettings();
  const changedLayout =
    next.layout !== settings.value.layout || next.double !== settings.value.double;
  settings.value.size = next.size;
  settings.value.color = next.color;
  if (changedLayout) void place(next.layout, next.double).catch(() => {});
}
async function close() {
  await bridge?.core.invoke('close_desktop_lyrics').catch(() => {});
}
onMounted(async () => {
  if (!bridge) return;
  if (settingsWindow) {
    try {
      await bridge.core.invoke('desktop_lyrics_settings_window', { show: true });
      settingsPanel.value?.focus();
    } catch {
      dismissMenu();
    }
    return;
  }
  window.addEventListener('storage', syncSettings);
  try {
    const stopMenu = await bridge.event.listen<boolean>(
      'desktop-lyrics-settings-visible',
      ({ payload }) => {
        menu.value = payload;
      },
    );
    if (!alive) {
      stopMenu();
      return;
    }
    unlisteners.push(stopMenu);
    const stop = await bridge.event.listen<Position>('desktop-lyrics-moved', ({ payload }) => {
      if (movingLayout.value) return;
      settings.value.positions[settings.value.layout] = payload;
      save();
    });
    if (!alive) {
      stop();
      return;
    }
    unlisteners.push(stop);
    const initial = new Promise<void>((resolve) => {
      ready = resolve;
    });
    channel.postMessage('snapshot');
    await place(settings.value.layout, settings.value.double);
    let timeout: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([
      initial,
      new Promise<void>((resolve) => {
        timeout = setTimeout(resolve, 500);
      }),
    ]);
    clearTimeout(timeout);
    ready = undefined;
    if (alive) await bridge.core.invoke('show_desktop_lyrics');
  } catch {
    void close();
  }
});
onUnmounted(() => {
  alive = false;
  window.removeEventListener('storage', syncSettings);
  unlisteners.forEach((stop) => stop());
  channel.close();
});
</script>

<template>
  <main
    v-if="!settingsWindow"
    class="overlay"
    data-tauri-drag-region="deep"
    :class="{ vertical, double: !vertical && settings.double, 'menu-open': menu }"
    :style="{ '--lyric-color': settings.color, '--lyric-size': settings.size + 'px' }"
    @keydown.esc="dismissMenu"
    @pointerdown.self="dismissMenu"
  >
    <div
      class="lines"
      @pointerdown="dismissMenu"
    >
      <div
        class="current"
        :title="snapshot.current"
      >
        {{ snapshot.available ? snapshot.current : '暂无歌词' }}
      </div>
      <div
        v-if="!vertical && settings.double"
        class="next"
        :title="snapshot.next"
      >
        {{ snapshot.next }}
      </div>
    </div>
    <div
      class="tools"
      role="group"
      aria-label="桌面歌词操作"
    >
      <button
        title="上一首"
        aria-label="上一首"
        :disabled="!playback?.canPrevious"
        @click="play('previous')"
      >
        <Previous />
      </button>
      <button
        :title="playback?.label ?? '播放'"
        :aria-label="playback?.label ?? '播放'"
        :disabled="!playback?.canToggle"
        @click="play('toggle')"
      >
        <Pause v-if="playback?.playing" /><Play v-else />
      </button>
      <button
        title="下一首"
        aria-label="下一首"
        :disabled="!playback?.canNext"
        @click="play('next')"
      >
        <Next />
      </button>
      <span
        class="tools-divider"
        aria-hidden="true"
      ></span>
      <button
        disabled
        aria-label="锁定（暂未开放）"
      >
        <Lock />
      </button>
      <button
        ref="settingsButton"
        title="歌词设置"
        aria-label="歌词设置"
        :aria-expanded="menu"
        @click="toggleMenu"
      >
        <Gear />
      </button>
      <button
        title="关闭桌面歌词"
        aria-label="关闭桌面歌词"
        @click="close"
      >
        <Close />
      </button>
    </div>
  </main>

  <section
    v-else
    ref="settingsPanel"
    tabindex="-1"
    class="settings"
    aria-label="歌词设置"
    @keydown.esc="dismissMenu"
  >
    <header v-if="!colorMenu">
      <strong>歌词设置</strong>
      <button
        aria-label="关闭歌词设置"
        @click="dismissMenu"
      >
        <Close />
      </button>
    </header>
    <div
      v-if="!colorMenu"
      class="settings-list"
    >
      <div class="menu-row font-row">
        <span>字体大小</span>
        <div class="size-stepper">
          <button
            aria-label="减小字号"
            :disabled="settings.size <= 18"
            @click="font(-2)"
          >
            −
          </button>
          <output>{{ settings.size }}</output>
          <button
            aria-label="增大字号"
            :disabled="settings.size >= 42"
            @click="font(2)"
          >
            +
          </button>
        </div>
      </div>
      <button
        class="menu-row"
        :aria-expanded="colorMenu"
        aria-controls="desktop-lyric-colors"
        @click="colorMenu = !colorMenu"
      >
        <span>字体颜色</span>
        <span class="color-indicator">
          <i :style="{ background: settings.color }"></i>
          <Chevron />
        </span>
      </button>
      <button
        class="menu-row separated"
        @click="change(vertical ? 'horizontal' : 'vertical', settings.double)"
      >
        {{ vertical ? '横排显示' : '竖排显示' }}
      </button>
      <button
        class="menu-row"
        :disabled="vertical"
        @click="change('horizontal', !settings.double)"
      >
        {{ settings.double ? '切换单行' : '切换双行' }}
      </button>
    </div>
    <div
      v-if="colorMenu"
      id="desktop-lyric-colors"
      class="color-menu"
      role="group"
      aria-label="字体颜色"
    >
      <button
        class="menu-row back-row"
        @click="colorMenu = false"
      >
        <Chevron /> 返回设置
      </button>
      <button
        v-for="choice in colors"
        :key="choice.value"
        class="menu-row color-option"
        :aria-pressed="settings.color === choice.value"
        @click="color(choice.value)"
      >
        <i :style="{ background: choice.value }"></i>
        <span>{{ choice.name }}</span>
        <Check v-if="settings.color === choice.value" />
      </button>
    </div>
  </section>
</template>

<style>
html,
body,
#app {
  width: 100%;
  height: 100%;
  margin: 0;
  background: transparent;
  overflow: hidden;
}
.overlay {
  box-sizing: border-box;
  height: 100%;
  position: relative;
  overflow: hidden;
  border: 1px solid #e3f5f138;
  border-radius: 9px;
  background: #131a1a69;
  box-shadow: inset 0 1px #ffffff0d;
  user-select: none;
  cursor: grab;
  color: #f5f9f8;
  font:
    12px 'Microsoft YaHei UI',
    sans-serif;
}
.overlay:active {
  cursor: grabbing;
}
.overlay:hover,
.menu-open {
  border-color: #b3d5ce70;
}
.lines {
  position: absolute;
  inset: 39px 14px 7px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: center;
  color: var(--lyric-color);
  font:
    700 var(--lyric-size)/1.22 'Microsoft YaHei UI',
    sans-serif;
  text-shadow:
    0 1px 3px #000e,
    0 1px 7px #0009;
  -webkit-text-stroke: 0.35px #172020;
}
.lines > div {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.next {
  font-size: 0.76em;
  opacity: 0.7;
  margin-top: 5px;
}
.vertical .lines {
  top: 40px;
  align-items: center;
}
.vertical .current {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  max-height: 100%;
}
.tools {
  position: absolute;
  top: 5px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 2px;
  align-items: center;
  padding: 1px 3px;
  color: #fff;
  filter: drop-shadow(0 1px 2px #0008);
}
.tools-divider {
  width: 1px;
  height: 13px;
  background: #ffffff59;
  margin: 0 4px;
}
.overlay button {
  border: 0;
  border-radius: 5px;
  color: inherit;
  background: transparent;
  font: inherit;
  white-space: nowrap;
  cursor: pointer;
}
.overlay button:hover,
.overlay button[aria-pressed='true'] {
  background: #ffffff24;
}
.overlay button:disabled {
  opacity: 0.45;
  cursor: default;
}
.overlay button:focus-visible {
  outline: 2px solid #adf0dd;
  outline-offset: 1px;
}
.tools button {
  width: 26px;
  height: 27px;
  padding: 0;
  display: grid;
  place-items: center;
  font-size: 16px;
}
.vertical .tools {
  gap: 0;
}
.vertical .tools button {
  width: 23px;
}
.settings {
  box-sizing: border-box;
  max-height: 100vh;
  overflow: auto;
  width: 100%;
  padding: 8px;
  background: #fbfcfb;
  color: #1f2927;
  border: 1px solid #dce2df;
  border-radius: 10px;
  font:
    14px 'Microsoft YaHei UI',
    sans-serif;
}
.settings:focus {
  outline: none;
}
.settings header {
  display: flex;
  padding: 0 9px;
  height: 34px;
  align-items: center;
  justify-content: space-between;
}
.settings header button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
}
.settings button {
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
}
.settings button:disabled {
  opacity: 0.45;
  cursor: default;
}
.settings .menu-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  height: 40px;
  padding: 0 9px;
  text-align: left;
  box-sizing: border-box;
}
.settings .menu-row.separated {
  border-top: 1px solid #edf0ee;
  border-radius: 0;
}
.settings button:hover:not(:disabled),
.settings button[aria-pressed='true'] {
  background: #eaf0ed;
}
.settings button:focus-visible {
  outline: 2px solid #39866b;
  outline-offset: -2px;
}
.size-stepper,
.color-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
}
.size-stepper button {
  width: 27px;
  height: 27px;
  padding: 0;
  border: 1px solid #dce2df;
}
.size-stepper output {
  min-width: 22px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.color-indicator i,
.color-option i {
  width: 13px;
  height: 13px;
  border: 1px solid #24312c40;
  border-radius: 50%;
  flex: none;
}
.settings .color-menu .menu-row {
  height: 35px;
  justify-content: flex-start;
}
.color-option svg {
  width: 15px;
  color: #28805c;
  margin-left: auto;
}
.back-row svg {
  transform: rotate(180deg);
}
</style>

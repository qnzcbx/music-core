<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import Previous from '~icons/lucide/skip-back';
import Next from '~icons/lucide/skip-forward';
import Play from '~icons/lucide/play';
import Pause from '~icons/lucide/pause';
import Lock from '~icons/lucide/lock';
import Gear from '~icons/lucide/settings-2';
import Close from '~icons/lucide/x';
import { bridge, lyricChannel } from '../composables/useDesktopLyrics';
import { acceptSnapshot, lyricSnapshot, type PlaybackAction, type Update } from '../player/desktop-lyrics';

const storageKey = 'musiccore:desktop-lyrics:settings:v1';
const colors = [
  { name:'白色', value:'#ffffff' }, { name:'暖黄', value:'#ffe095' },
  { name:'薄荷绿', value:'#a9f1d0' }, { name:'浅蓝', value:'#a9dbff' }, { name:'桃粉', value:'#ffc3d8' },
];
type Position = [number, number];
type Layout = 'horizontal' | 'vertical';
function readSettings() {
  let raw;
  try { raw = JSON.parse(localStorage.getItem(storageKey) ?? '{}') ?? {}; } catch { raw = {}; }
  const position = (value: unknown): Position | null =>
    Array.isArray(value) && value.length === 2 && value.every(n => Number.isInteger(n) && Math.abs(n) <= 2147483647)
      ? [value[0], value[1]] : null;
  return {
    size: Number.isInteger(raw.size) ? Math.min(42, Math.max(18, raw.size)) : 28,
    color: colors.find(color => color.value === raw.color)?.value ?? colors[0]!.value,
    layout: (raw.layout === 'vertical' ? 'vertical' : 'horizontal') as Layout,
    double: raw.double === true,
    positions: { horizontal: position(raw.positions?.horizontal), vertical: position(raw.positions?.vertical) }
  };
}
const settings = ref(readSettings());
const vertical = computed(() => settings.value.layout === 'vertical');
const menu = ref(false), movingLayout = ref(false);
const update = ref<Update>({sequence:0, snapshot:lyricSnapshot(null,null,0)});
const snapshot = computed(() => update.value.snapshot);
const playback = computed(() => update.value.playback);
const settingsButton = ref<HTMLButtonElement>();
function play(action: PlaybackAction) { channel.postMessage({type:'playback', action}); }
function dismissMenu() {
  if (!menu.value) return;
  menu.value = false;
  settingsButton.value?.focus();
}
const channel = new BroadcastChannel(lyricChannel);
let ready: (()=>void) | undefined;
channel.onmessage = ({data}) => {
  if (data?.snapshot) { update.value = acceptSnapshot(update.value, data); ready?.(); }
};
let alive = true, unlisten: (()=>void) | undefined;
function save() {
  try { localStorage.setItem(storageKey, JSON.stringify(settings.value)); } catch { /* retain session settings */ }
}
function font(delta:number) { settings.value.size = Math.min(42, Math.max(18, settings.value.size + delta)); save(); }
function color(value:string) { settings.value.color = value; save(); }
async function place(layout: Layout, double: boolean) {
  if (movingLayout.value || !bridge) return;
  movingLayout.value = true;
  try {
    const pos = await bridge.core.invoke<Position>('place_desktop_lyrics', {
      vertical: layout === 'vertical', double, saved: settings.value.positions[layout],
    });
    Object.assign(settings.value, {layout, double});
    settings.value.positions[layout] = pos;
    save();
  } finally { movingLayout.value = false; }
}
async function change(layout: Layout, double: boolean) {
  try { await place(layout,double); } catch { /* keep last valid layout */ }
}
async function close() { await bridge?.core.invoke('close_desktop_lyrics').catch(() => {}); }
onMounted(async () => {
  if (!bridge) return;
  try {
    const stop = await bridge.event.listen<Position>('desktop-lyrics-moved', ({payload}) => {
      if (movingLayout.value) return;
      settings.value.positions[settings.value.layout] = payload;
      save();
    });
    if (!alive) { stop(); return; }
    unlisten = stop;
    const initial = new Promise<void>(resolve => { ready = resolve; });
    channel.postMessage('snapshot');
    await place(settings.value.layout, settings.value.double);
    let timeout: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([initial, new Promise<void>(resolve => { timeout = setTimeout(resolve, 500); })]);
    clearTimeout(timeout);
    ready = undefined;
    if (alive) await bridge.core.invoke('show_desktop_lyrics');
  } catch { void close(); }
});
onUnmounted(() => { alive = false; unlisten?.(); channel.close(); });
</script>

<template>
  <main class="overlay" data-tauri-drag-region="deep" :class="{ vertical, double: !vertical && settings.double, 'menu-open': menu }"
    :style="{ '--lyric-color':settings.color, '--lyric-size':settings.size + 'px' }"
    @keydown.esc="dismissMenu" @pointerdown.self="menu = false">
    <div class="lines" @pointerdown="menu = false">
      <div class="current" :title="snapshot.current">{{ snapshot.available ? snapshot.current : '暂无歌词' }}</div>
      <div v-if="!vertical && settings.double" class="next" :title="snapshot.next">{{ snapshot.next }}</div>
    </div>
    <div class="tools" role="group" aria-label="桌面歌词操作">
      <button title="上一首" aria-label="上一首" :disabled="!playback?.canPrevious" @click="play('previous')"><Previous /></button>
      <button :title="playback?.label ?? '播放'" :aria-label="playback?.label ?? '播放'" :disabled="!playback?.canToggle" @click="play('toggle')">
        <Pause v-if="playback?.playing" /><Play v-else />
      </button>
      <button title="下一首" aria-label="下一首" :disabled="!playback?.canNext" @click="play('next')"><Next /></button>
      <span class="tools-divider" aria-hidden="true"></span>
      <button disabled aria-label="锁定（暂未开放）"><Lock /></button>
      <button ref="settingsButton" title="歌词设置" aria-label="歌词设置" :aria-expanded="menu" aria-controls="desktop-lyric-settings" @click="menu = !menu"><Gear /></button>
      <button title="关闭桌面歌词" aria-label="关闭桌面歌词" @click="close"><Close /></button>
    </div>
    <section v-if="menu" id="desktop-lyric-settings" class="settings" data-tauri-drag-region="false" aria-label="歌词设置">
      <div class="group"><span>字体大小</span><button aria-label="减小字号" :disabled="settings.size <= 18" @click="font(-2)">−</button><output>{{ settings.size }}</output><button aria-label="增大字号" :disabled="settings.size >= 42" @click="font(2)">+</button></div>
      <div class="group palette"><span>字体颜色</span><button v-for="choice in colors" :key="choice.value" :title="choice.name" :aria-label="choice.name" :aria-pressed="settings.color === choice.value" :style="{ '--swatch':choice.value }" @click="color(choice.value)" /></div>
      <button class="setting-action" @click="change(vertical ? 'horizontal' : 'vertical', settings.double)">{{ vertical ? '横排显示' : '竖排显示' }}</button>
      <button class="setting-action" :disabled="vertical" @click="change('horizontal', !settings.double)">{{ settings.double ? '切换单行' : '切换双行' }}</button>
    </section>
  </main>
</template>

<style>
html, body, #app { width: 100%; height: 100%; margin: 0; background: transparent; overflow: hidden; }
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
  font: 12px "Microsoft YaHei UI", sans-serif;
}
.overlay:active { cursor: grabbing; }
.overlay:hover, .menu-open { border-color: #b3d5ce70; }
.lines { position: absolute; inset: 39px 14px 7px; display: flex; flex-direction: column; justify-content: center; text-align: center; color: var(--lyric-color); font: 700 var(--lyric-size)/1.22 "Microsoft YaHei UI", sans-serif; text-shadow: 0 1px 3px #000e, 0 1px 7px #0009; -webkit-text-stroke: .35px #172020; }
.lines > div { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.next { font-size: .76em; opacity: .7; margin-top: 5px; }
.vertical .lines { top: 40px; align-items: center; }
.vertical .current { writing-mode: vertical-rl; text-orientation: mixed; max-height: 100%; }
.tools { position: absolute; top: 5px; left: 50%; transform: translateX(-50%); display: flex; gap: 2px; align-items: center; padding: 1px 3px; color: #fff; filter: drop-shadow(0 1px 2px #0008); }
.tools-divider { width: 1px; height: 13px; background: #ffffff59; margin: 0 4px; }
.overlay button { border: 0; border-radius: 5px; color: inherit; background: transparent; font: inherit; white-space: nowrap; cursor: pointer; }
.overlay button:hover, .overlay button[aria-pressed=true] { background: #ffffff24; }
.overlay button:disabled { opacity: .45; cursor: default; }
.overlay button:focus-visible { outline: 2px solid #adf0dd; outline-offset: 1px; }
.tools button { width: 26px; height: 27px; padding: 0; display: grid; place-items: center; font-size: 16px; }
.vertical .tools { gap: 0; }
.vertical .tools button { width: 23px; }
.settings {
  cursor: default; position: absolute; z-index: 1; top: 36px; right: max(5px, calc(50% - 65px));
  width: max-content; max-width: calc(100% - 10px); box-sizing: border-box;
  padding: 5px; border-radius: 8px; background: #f4f7f6; color: #1c2928;
  border: 1px solid #1c292827; box-shadow: 0 3px 12px #0005;
  display: grid; grid-template-columns: auto auto; gap: 2px 5px;
}
.group { display: flex; align-items: center; gap: 4px; min-height: 26px; padding: 0 5px; }
.group span { color: #435653; margin-right: 2px; }
.settings button:hover:not(:disabled) { background: #16352c17; }
.group button { padding: 3px 5px; }
.group output { min-width: 16px; text-align: center; font-variant-numeric: tabular-nums; }
.palette button { padding: 0; width: 13px; height: 13px; border: 1px solid #0004; border-radius: 50%; background: var(--swatch) !important; }
.palette button[aria-pressed=true] { outline: 1px solid #1c2928; outline-offset: 1px; }
.settings .setting-action { min-height: 23px; padding: 3px 5px; text-align: left; }
.vertical .settings { grid-template-columns: 1fr; right: 5px; gap: 3px; }
</style>

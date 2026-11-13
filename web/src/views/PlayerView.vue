<script setup lang="ts">
import { computed, watch, onUnmounted, ref } from "vue";
import LyricPanel from "../components/LyricPanel.vue";
import AmbientBackground from "../components/AmbientBackground.vue";
import VinylPlayer from "../components/VinylPlayer.vue";
import CollapseIcon from "~icons/lucide/chevron-down";
import ReturnIcon from "~icons/lucide/undo-2";
import { useImmersiveControls } from "../composables/useImmersiveControls";
import BottomPlayer from "../components/BottomPlayer.vue";
import { useCoreClient } from "../composables/useCoreClient";
import { usePlayerVisuals } from "../composables/usePlayerTransition";
const { player, lyrics } = useCoreClient();
const {
  palette,
  phase,
  layout,
  selectLayout,
  lyricAlignment,
  selectLyricAlignment,
  close,
  setPanel,
  setBackButton,
  setLargeCover,
} = usePlayerVisuals();
const song = player.selected;
const root = ref<HTMLElement>(),
  controls = ref<HTMLElement>();
const eligible = computed(
  () =>
    player.playing.value && player.phase.value === "ready" && player.message.value !== "正在缓冲",
);
const chrome = useImmersiveControls(root, controls, eligible);
const backgroundPalette = computed(() => {
  if (palette.value.evidence !== "fallback") return palette.value;
  const tints =
    layout.value === "vinyl-wide"
      ? ["#dedfe1", "#ecebed"]
      : layout.value === "square-cover"
        ? ["#e4dfdc", "#efece7"]
        : layout.value === "lyrics-only"
          ? ["#e6e4e0", "#f2f0ed"]
          : ["#e1e1dc", "#f0eeea"];
  return {
    ...palette.value,
    key: "neutral-" + layout.value,
    baseLeft: tints[0]!,
    baseRight: tints[1]!,
    left: tints[0]!,
    right: tints[1]!,
  };
});
const lines = computed(() => lyrics.state.value.document?.lines ?? []);
let coverElement: unknown, squareElement: unknown;
function updateCover() {
  setLargeCover(
    !song.value || layout.value === "lyrics-only"
      ? null
      : layout.value === "square-cover"
        ? squareElement
        : coverElement,
  );
}
function registerCover(element: unknown) {
  coverElement = element;
  updateCover();
}
function registerSquare(element: unknown) {
  squareElement = element;
  updateCover();
}
watch([song, layout], updateCover, { flush: "post" });
onUnmounted(() => {
  setLargeCover(null);
  setPanel(null);
  setBackButton(null);
});
</script>
<template>
  <section
    ref="root"
    class="immersive-player"
    :data-controls-hidden="chrome.hidden.value"
    :class="{ 'wide-player': layout === 'vinyl-wide' }"
    :data-player-layout="layout"
    :data-lyric-alignment="lyricAlignment"
    aria-label="沉浸式播放器"
    :style="{
      '--player-accent': palette.accent,
      '--layout-preview-left': palette.left,
      '--layout-preview-right': palette.right,
      '--player-lyric-align': lyricAlignment,
    }"
  >
    <AmbientBackground :palette="backgroundPalette" />
    <header class="immersive-topbar">
      <button
        :ref="setBackButton"
        class="collapse-player"
        aria-label="收起歌曲详情页"
        title="收起歌曲详情页"
        @click="close"
      >
        <CollapseIcon />
      </button>
    </header>
    <div
      v-if="song"
      :ref="setPanel"
      class="immersive-content"
      :class="
        layout === 'vinyl-wide'
          ? 'wide-layout grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,44fr)_minmax(0,56fr)]'
          : layout === 'square-cover'
            ? 'square-layout grid grid-cols-1 gap-8 lg:grid-cols-2'
            : layout === 'lyrics-only'
              ? 'lyrics-layout'
              : 'classic-layout'
      "
    >
      <div class="record-column">
        <div
          id="player-square-cover"
          :ref="registerSquare"
          class="square-cover-surface"
          :aria-hidden="layout !== 'square-cover'"
        />
        <VinylPlayer
          :cover="song.cover"
          :playing="player.playing.value"
          :palette="palette"
          :label="song.name"
          :layout="layout"
          @cover-element="registerCover"
        />
      </div>
      <div class="listening-column">
        <div class="immersive-identity">
          <h1>{{ song.title || song.name }}</h1>
          <p class="immersive-artist">{{ song.artist }}</p>
          <p class="immersive-album">{{ song.album && song.album !== "NULL" ? song.album : "" }}</p>
        </div>
        <LyricPanel
          :key="player.queue.current.value ?? ''"
          :lines="lines"
          :current-time="player.time.value"
          :loading="lyrics.state.value.loading"
          :error="lyrics.state.value.error"
          :plain-text="lyrics.state.value.document?.plainText ?? ''"
          :unaligned-translation="lyrics.state.value.document?.unalignedTranslation"
          :status="lyrics.state.value.document?.status"
          :alignment="lyricAlignment"
          :duration="player.duration.value"
          @seek="player.seek"
          @retry="lyrics.retry"
        />
      </div>
    </div>
    <div v-else :ref="setPanel" class="player-empty">
      <h1>还没有正在播放的歌曲</h1>
      <p>从搜索或播放队列选择歌曲</p>
      <button
        class="empty-return"
        aria-label="收起歌曲详情页"
        title="收起歌曲详情页"
        @click="close"
      >
        <ReturnIcon width="24" height="24" />
      </button>
    </div>
    <div
      ref="controls"
      class="immersive-control-layer"
      :class="{ 'controls-hidden': chrome.hidden.value }"
      @pointerenter="
        (event) => {
          if (event.pointerType === 'mouse') chrome.hold(true);
        }
      "
      @pointerleave="chrome.hold(false)"
      @focusin="chrome.focusIn"
      @focusout="chrome.focusOut"
    >
      <BottomPlayer immersive @lock-change="chrome.locked.value = $event" />
    </div>
  </section>
</template>
<style scoped>
.immersive-player {
  color-scheme: light;
  --player-text: #283c32;
  --player-text-muted: #53634f;
  --player-control: #3e5344;
  --player-lyric: #465848;
  --player-lyric-near: #344e3c;
  --player-error: #873e35;
  --player-focus: #77946c;
  --player-highlight: #c9ddafaa;
  --player-surface: #f5f6eefa;
  --player-border: #c4cebd;
  /* 控制区沿用唱片空间的可读性变量。 */
  --app-text: var(--player-text);
  --app-text-muted: var(--player-text-muted);
  --app-link: var(--player-control);
  --app-focus: var(--player-focus);
  --app-danger: var(--player-error);
  --app-surface: #dfe8d9;
  --app-surface-raised: var(--player-surface);
  --app-selected: #e5eadf;
  --app-border: var(--player-border);
  --app-border-strong: var(--player-border);
  --app-accent: #547c5c;
  --app-success-bg: #e5eadf;
  --app-shadow-panel: 0 12px 30px #2d4c3020;
  position: fixed;
  inset: 0;
  z-index: 3;
  color: var(--player-text);
  overflow: auto;
  padding: 100px clamp(24px, 6vw, 100px) calc(var(--mini-player-height, 116px) + 24px);
}
.immersive-topbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 2;
  padding: 24px 34px;
  border: 0;
  color: var(--player-control);
}
.collapse-player {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 12px;
  border: 0;
  border-radius: 20px;
  background: #ffffff38;
  color: inherit;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.collapse-player span {
  font:
    24px/12px Georgia,
    serif;
  margin-top: -5px;
}
.collapse-player:hover {
  background: #ffffff70;
}
.immersive-wordmark {
  font:
    italic 15px Georgia,
    serif;
  letter-spacing: 0.5px;
}
.immersive-wordmark i {
  margin: 0 9px;
  opacity: 0.45;
}
.player-menu {
  position: relative;
}
.immersive-settings {
  display: flex;
  align-items: center;
  gap: 8px;
}
.player-menu summary {
  list-style: none;
  padding: 6px 12px;
  font:
    20px Georgia,
    serif;
  cursor: pointer;
}
.player-menu summary::-webkit-details-marker {
  display: none;
}
.player-menu > div {
  position: absolute;
  top: 38px;
  right: 0;
  width: 152px;
  padding: 8px;
  border: 1px solid var(--player-border);
  border-radius: 12px;
  background: var(--player-surface);
  box-shadow: 0 12px 30px #2d4c3020;
}
.player-menu a {
  display: block;
  padding: 10px;
  color: #39503d;
  text-decoration: none;
  font-size: 12px;
  border-radius: 6px;
}
.player-menu a:hover {
  background: #dfe8d9;
}
.immersive-content {
  position: relative;
  min-height: calc(100dvh - var(--mini-player-height, 116px) - 154px);
  margin: auto;
}
.classic-layout {
  display: grid;
  grid-template-columns: minmax(290px, 1fr) minmax(300px, 1fr);
  align-items: center;
  gap: clamp(38px, 8vw, 130px);
  max-width: 1160px;
}
.record-column {
  align-self: center;
}
.listening-column {
  min-width: 0;
  padding-top: 10px;
}
.immersive-identity {
  text-align: center;
  margin-bottom: 24px;
}
.listening-kicker {
  color: var(--player-text-muted);
  font-size: 11px;
  letter-spacing: 4px;
  margin: 0 0 18px;
}
.immersive-identity h1 {
  font:
    500 clamp(27px, 2.8vw, 39px)/1.4 "Songti SC",
    SimSun,
    serif;
  margin: 0 0 10px;
  overflow-wrap: anywhere;
}
.immersive-artist {
  font-size: 16px;
  margin: 0 0 9px;
  color: var(--player-text);
}
.immersive-album {
  color: var(--player-text-muted);
  font-size: 12px;
  margin: 0;
}
.listening-column :deep(.lyric-scroll) {
  --lyric-height: clamp(220px, 42dvh, 450px);
  text-align: var(--player-lyric-align, center);
  mask-image: linear-gradient(transparent, black 14%, black 86%, transparent);
}
.listening-column :deep(.lyric-line) {
  text-align: var(--player-lyric-align, center);
  white-space: pre-line;
}
.listening-column :deep(.lyric-scroll li) {
  color: var(--player-lyric);
  opacity: 1;
  font-size: 18px;
  line-height: 1.7;
  padding: 15px 6px;
}
.listening-column :deep(.lyric-scroll li.lyric-current) {
  color: var(--player-active-color, var(--player-accent));
  font-size: 23px;
  font-weight: 700;
}
.listening-column :deep(.lyric-scroll li.lyric-near) {
  color: var(--player-lyric-near);
}
.listening-column :deep(.lyric-toolbar) {
  color: var(--player-text-muted);
  height: 34px;
  font-size: 10px;
}
.listening-column :deep(.lyric-toolbar button) {
  background: #ffffff50;
  border-radius: 14px;
  padding: 5px 9px;
  color: var(--player-control);
}
.media-failure {
  background: #fffaf3ac;
  border-radius: 12px;
  padding: 12px 16px;
  font-size: 12px;
  color: var(--player-error);
}
.media-failure button {
  color: inherit;
  background: transparent;
  border: 0;
  text-decoration: underline;
  cursor: pointer;
}
.not-current {
  text-align: center;
  padding: 80px 10px;
  font-size: 13px;
}
.player-empty {
  position: relative;
  max-width: 620px;
  margin: 20vh auto 0;
  text-align: center;
  line-height: 1.8;
}
.player-empty h1 {
  font:
    28px "Songti SC",
    SimSun,
    serif;
}
.player-empty p {
  font-size: 13px;
}
.empty-return {
  appearance: none;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  margin: 12px auto 0;
  padding: 10px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--player-control);
  opacity: 0.65;
  cursor: pointer;
  transition: opacity 0.12s ease;
}
.empty-return:hover,
.empty-return:focus-visible {
  opacity: 1;
}
.empty-return:focus-visible {
  outline: 2px solid var(--player-focus);
  outline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .empty-return {
    transition: none;
  }
}
@media (max-width: 760px) {
  .immersive-player {
    padding: 76px 22px calc(var(--mini-player-height, 160px) + 26px);
  }
  .immersive-topbar {
    padding: 16px 18px;
  }
  .immersive-wordmark {
    font-size: 12px;
  }
  .immersive-wordmark i {
    margin: 0 4px;
  }
  .classic-layout {
    grid-template-columns: 1fr;
    gap: 28px;
    min-height: 0;
  }
  .listening-column {
    padding-top: 0;
  }
  .immersive-identity {
    margin-bottom: 16px;
  }
  .immersive-identity h1 {
    font-size: 25px;
  }
  .listening-kicker {
    margin-bottom: 12px;
  }
  .listening-column :deep(.lyric-scroll) {
    --lyric-height: 240px;
  }
  .listening-column :deep(.lyric-scroll li) {
    font-size: 16px;
  }
  .listening-column :deep(.lyric-scroll li.lyric-current) {
    font-size: 20px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .immersive-player {
    scroll-behavior: auto;
  }
}
/* 大唱片延伸到视口之外。 */
.wide-player {
  overflow-x: clip;
}
.wide-player .immersive-settings :deep(summary) {
  background: var(--player-surface);
  border-radius: 8px;
}
.wide-layout .record-column {
  position: fixed;
  top: -36vh;
  right: -20vw;
  width: clamp(720px, 52vw, 1380px);
  aspect-ratio: 1;
  pointer-events: none;
}
.wide-layout .listening-column {
  position: relative;
  z-index: 1;
  min-width: 0;
  padding-top: clamp(20px, 4vh, 64px);
}
.wide-layout .immersive-identity {
  text-align: left;
  margin: 0 0 28px;
}
.wide-layout .listening-kicker {
  letter-spacing: 3px;
  font-size: 10px;
  margin-bottom: 16px;
}
.wide-layout .immersive-identity h1 {
  font-size: clamp(29px, 3vw, 44px);
  line-height: 1.35;
}
.wide-layout .immersive-artist {
  font-size: 15px;
}
.wide-layout .immersive-album {
  margin-top: 8px;
}
.wide-layout :deep(.lyric-toolbar) {
  justify-content: flex-start;
  gap: 18px;
}
.wide-layout :deep(.lyric-scroll) {
  --lyric-height: clamp(280px, 48dvh, 580px);
  text-align: var(--player-lyric-align, left);
  mask-image: linear-gradient(transparent, black 10%, black 74%, transparent);
}
.wide-layout :deep(.lyric-scroll ol) {
  padding-inline: 0 12px;
}
.wide-layout :deep(.lyric-line) {
  text-align: var(--player-lyric-align, left);
  white-space: pre-line;
}
.wide-layout :deep(.lyric-scroll li) {
  opacity: 0.36;
  font-size: clamp(17px, 1.5vw, 22px);
  padding: 12px 2px;
  white-space: pre-line;
}
.wide-layout :deep(.lyric-scroll li.lyric-near) {
  opacity: 0.7;
}
.wide-layout :deep(.lyric-scroll li.lyric-current) {
  opacity: 1;
  font-size: clamp(20px, 1.7vw, 26px);
}
@media (max-width: 1023px) {
  .wide-player {
    padding-top: 88px;
  }
  .wide-layout {
    min-height: 0;
  }
  .wide-layout .record-column {
    position: relative;
    top: auto;
    right: auto;
    width: min(44vw, 320px);
    justify-self: center;
  }
  .wide-layout .listening-column {
    padding-top: 0;
  }
  .wide-layout .immersive-identity {
    text-align: center;
  }
  .wide-layout :deep(.lyric-scroll) {
    --lyric-height: clamp(240px, 40dvh, 390px);
  }
}
@media (max-width: 600px) {
  .immersive-wordmark {
    display: none;
  }
  .immersive-settings :deep(.theme-settings fieldset) {
    position: fixed;
    top: 62px;
    right: 18px;
    margin-top: 0;
    max-width: calc(100vw - 36px);
    box-sizing: border-box;
  }
  .wide-layout {
    gap: 24px;
  }
  .wide-layout .record-column {
    width: min(46vw, 196px);
  }
  .wide-layout :deep(.lyric-scroll) {
    --lyric-height: clamp(180px, 30dvh, 250px);
  }
  .wide-layout .immersive-identity h1 {
    font-size: 27px;
  }
  .wide-layout .immersive-identity {
    margin-bottom: 16px;
  }
}
@media (max-width: 600px) and (max-height: 740px) {
  .wide-player {
    padding-top: 70px;
  }
  .wide-layout {
    gap: 16px;
  }
  .wide-layout .record-column {
    width: 130px;
  }
  .wide-layout .listening-kicker,
  .wide-layout .immersive-album {
    display: none;
  }
  .wide-layout :deep(.lyric-scroll) {
    --lyric-height: 180px;
  }
}
/* 封面传送到方形容器时保留原唱片旋转器。 */
.square-cover-surface {
  display: none;
}
.square-layout {
  align-items: center;
  max-width: 1160px;
  gap: clamp(38px, 8vw, 130px);
}
.square-layout .record-column {
  position: relative;
  min-width: 0;
}
.square-layout .square-cover-surface {
  display: block;
  width: min(100%, 420px);
  aspect-ratio: 1;
  margin: auto;
  border-radius: 10px;
  background: var(--player-surface);
  box-shadow: 0 16px 36px #243d291c;
}
.square-layout :deep(.square-cover-surface img) {
  object-fit: contain;
}
.square-layout :deep(.square-cover-surface .cover-fallback) {
  background: var(--player-surface);
}
.square-layout :deep(.vinyl-scene),
.lyrics-layout :deep(.vinyl-scene) {
  position: absolute;
  top: 0;
  left: 0;
  visibility: hidden;
  pointer-events: none;
}
.lyrics-layout {
  max-width: 820px;
}
.lyrics-layout .record-column {
  position: absolute;
  width: 448px;
  height: 448px;
  visibility: hidden;
  pointer-events: none;
}
.lyrics-layout .listening-column {
  padding-top: 20px;
}
.lyrics-layout .immersive-identity {
  margin-bottom: 24px;
}
.lyrics-layout :deep(.lyric-scroll) {
  --lyric-height: clamp(320px, 54dvh, 620px);
}
@media (max-width: 1023px) {
  .square-layout {
    min-height: 0;
    gap: 28px;
  }
  .square-layout .square-cover-surface {
    width: min(44vw, 320px);
  }
}
@media (max-width: 600px) {
  .square-layout {
    gap: 22px;
  }
  .square-layout .square-cover-surface {
    width: min(46vw, 196px);
  }
  .square-layout :deep(.lyric-scroll) {
    --lyric-height: clamp(180px, 30dvh, 250px);
  }
  .lyrics-layout .listening-column {
    padding-top: 10px;
  }
  .lyrics-layout :deep(.lyric-scroll) {
    --lyric-height: clamp(260px, 50dvh, 440px);
  }
  .lyrics-layout .record-column {
    width: 1px;
    height: 1px;
    overflow: hidden;
  }
}
@media (max-width: 600px) and (max-height: 740px) {
  .square-layout .square-cover-surface {
    width: 130px;
  }
}
</style>
<style scoped>
.immersive-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.immersive-settings {
  flex-shrink: 0;
}
.listening-column :deep(.lyric-scroll li) {
  opacity: 0.38;
}
.listening-column :deep(.lyric-scroll li.lyric-near) {
  opacity: 0.72;
}
.listening-column :deep(.lyric-scroll li.lyric-current) {
  opacity: 1;
}
@media (max-width: 600px) {
  .classic-layout :deep(.vinyl-scene) {
    width: min(46vw, 196px);
    padding-top: 0;
  }
  .classic-layout {
    gap: 16px;
  }
  .classic-layout .immersive-identity {
    margin-bottom: 8px;
  }
  .classic-layout .listening-kicker {
    display: none;
  }
  .classic-layout .immersive-artist {
    font-size: 13px;
  }
  .classic-layout .immersive-album {
    display: none;
  }
  .classic-layout :deep(.lyric-scroll) {
    --lyric-height: 230px;
  }
  .immersive-player {
    padding-bottom: 180px;
  }
  .immersive-settings {
    gap: 4px;
  }
}
</style>

<style scoped>
.immersive-control-layer {
  position: relative;
  z-index: 25;
  opacity: 1;
  visibility: visible;
  transition:
    opacity 0.3s ease,
    visibility 0.3s;
}
.immersive-control-layer.controls-hidden {
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}
.collapse-player {
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 10px;
  opacity: 0.65;
}
.collapse-player svg {
  width: 24px;
  height: 24px;
}
.collapse-player:hover,
.collapse-player:focus-visible {
  opacity: 1;
}
.immersive-player {
  --player-text: #29333b;
  --player-text-muted: #52606b;
  --player-control: #3b4d59;
  --player-lyric: #485660;
  --player-lyric-near: #34414a;
  --player-active-color: #263540;
  --player-surface: #faf9f5e8;
  --player-border: #c9cecf;
  --player-focus: #5b717d;
  --app-surface: #eeefed;
  --app-selected: #e2e5e5;
  --app-accent: #526b77;
}
.immersive-player[data-player-layout="vinyl-wide"] :deep(.ambient-layer) {
  background:
    radial-gradient(ellipse 80% 100% at 95% 75%, var(--ambient-left), transparent 80%),
    linear-gradient(120deg, var(--ambient-base-right), var(--ambient-base-left));
}
.immersive-player[data-player-layout="square-cover"] :deep(.ambient-layer) {
  background:
    radial-gradient(ellipse 60% 90% at 20% 45%, var(--ambient-left), transparent 85%),
    linear-gradient(150deg, var(--ambient-base-left), var(--ambient-base-right));
}
.immersive-player[data-player-layout="lyrics-only"] :deep(.ambient-layer) {
  background:
    radial-gradient(ellipse 70% 70% at 50% 45%, var(--ambient-center), transparent 90%),
    linear-gradient(160deg, var(--ambient-base-left), var(--ambient-base-right));
}
@media (prefers-reduced-motion: reduce) {
  .immersive-control-layer {
    transition: none;
  }
}
</style>

<style scoped>
.immersive-control-layer{background:transparent;border:0;box-shadow:none;backdrop-filter:none}.immersive-control-layer::before,.immersive-control-layer::after{content:none;display:none}
</style>

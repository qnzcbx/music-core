<script setup lang="ts">
import { nextTick, onUnmounted, ref, toRef, watch } from "vue";
import type { LyricLine } from "../types/core";
import { useLyricPresentation } from "../composables/useLyrics";
const canSeekLyric = (seconds: number, duration: number) =>
  Number.isFinite(seconds) && seconds >= 0 && duration > 0 && seconds < duration;
const props = defineProps<{
  lines: readonly LyricLine[];
  currentTime: number;
  loading: boolean;
  error: string;
  plainText: string;
  status?: string;
  alignment?: string;
  unalignedTranslation?: string | null;
  duration: number;
}>();
const emit = defineEmits<{ seek: [seconds: number]; retry: [] }>();
const { viewport, index, following, pauseFollowing, resumeFollowing, onKey, onScroll, center } =
  useLyricPresentation(toRef(props, "lines"), toRef(props, "currentTime"));
const clicked = ref(-1);
let animationTimer: ReturnType<typeof setTimeout> | undefined;
let clickGeneration = 0;
function clearClick() {
  clickGeneration++;
  clearTimeout(animationTimer);
  clicked.value = -1;
}
async function jump(i: number) {
  const line = props.lines[i];
  if (!line || !canSeekLyric(line.startMs / 1000, props.duration)) return;
  clearClick();
  const generation = clickGeneration;
  await nextTick();
  if (generation !== clickGeneration) return;
  clicked.value = i;
  emit("seek", line.startMs / 1000);
  resumeFollowing();
  animationTimer = setTimeout(() => {
    clicked.value = -1;
  }, 650);
}
watch(() => props.lines, clearClick);
watch(() => props.alignment, center, { flush: "post" });
onUnmounted(clearClick);
</script>
<template>
  <section id="lyric-panel" class="lyric-panel" aria-label="歌词面板">
    <div v-if="lines.length" class="lyric-toolbar">
      <span>
        {{ following ? "正在跟随播放" : "翻阅中 · 停止滚动 3 秒后自动跟随" }}
      </span>
      <button v-if="!following" @click="resumeFollowing">立即恢复</button>
    </div>
    <div
      ref="viewport"
      class="lyric-scroll no-scrollbar"
      tabindex="0"
      aria-label="可滚动歌词"
      @wheel.passive="pauseFollowing"
      @touchmove.passive="pauseFollowing"
      @keydown="onKey"
      @scroll.passive="onScroll"
    >
      <p v-if="loading" role="status">正在获取歌词…</p>
      <div v-else-if="error">
        <p class="error" role="alert">歌词加载失败：{{ error }}</p>
        <button @click="emit('retry')">重试歌词</button>
      </div>
      <template v-else-if="!lines.length && plainText">
        <p>歌词无时间戳，暂不支持同步</p>
        <pre>{{ plainText }}</pre>
      </template>
      <p v-else-if="!lines.length">
        {{ status === "instrumental" ? "纯音乐" : "暂无歌词" }}
      </p>
      <ol v-else>
        <li
          v-for="(line, i) in lines"
          :key="`${i}-${line.startMs / 1000}`"
          :aria-current="index >= 0 && line.startMs === lines[index]?.startMs ? 'true' : undefined"
          :class="{
            'lyric-current': index >= 0 && line.startMs === lines[index]?.startMs,
            'lyric-near': index >= 0 && Math.abs(i - index) === 1,
            'lyric-clicked': i === clicked,
          }"
        >
          <button
            class="lyric-line"
            :disabled="!canSeekLyric(line.startMs / 1000, duration)"
            :data-time="line.startMs / 1000"
            :aria-label="`跳转到歌词：${line.text || '间奏'}`"
            @keydown.space.stop
            @click="jump(i)"
          >
            {{ line.text || "♪ 间奏" }}
            <small v-if="line.translation" class="lyric-translation">
              {{ line.translation }}
            </small>
            <small v-if="line.romanization" class="lyric-romanization">
              {{ line.romanization }}
            </small>
          </button>
        </li>
      </ol>
      <pre v-if="unalignedTranslation" class="lyric-translation">
        {{ unalignedTranslation }}
      </pre>
    </div>
  </section>
</template>
<style scoped>
.lyric-panel {
  min-width: 0;
}
.lyric-toolbar {
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--player-text-muted, var(--app-text-muted));
  font-size: 12px;
}
.lyric-toolbar button {
  border: 1px solid var(--player-border, var(--app-border));
  background: var(--player-surface, var(--app-surface));
  color: var(--player-control, var(--app-link));
  padding: 7px 12px;
  cursor: pointer;
}
.lyric-scroll {
  --lyric-height: clamp(320px, 58svh, 568px);
  height: var(--lyric-height);
  overflow-y: auto;
  overscroll-behavior: contain;
  text-align: center;
  overflow-anchor: none;
  scroll-behavior: auto;
}
.lyric-scroll ol {
  list-style: none;
  /* 半个歌词窗口的留白，让首尾行也有足够空间居中。 */
  padding: calc(var(--lyric-height) / 2) 14px;
  margin: 0;
}
.lyric-scroll li {
  padding: 16px 8px;
  font-size: 18px;
  line-height: 1.8;
  color: var(--player-lyric, var(--app-text-muted));
  opacity: 0.32;
  overflow-wrap: anywhere;
}
.lyric-scroll li.lyric-near {
  opacity: 0.65;
}
.lyric-scroll li.lyric-current {
  font-size: 24px;
  font-weight: 700;
  color: var(--player-accent, var(--app-link));
  opacity: 1;
}
.lyric-scroll pre {
  white-space: pre-wrap;
  font: inherit;
  line-height: 1.8;
  padding: 20px;
}
.lyric-line {
  width: 100%;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  line-height: inherit;
  cursor: pointer;
}
.lyric-line:disabled {
  cursor: default;
}
.lyric-translation,
.lyric-romanization {
  display: block;
  white-space: pre-line;
  font-size: 0.62em;
  font-weight: 400;
  opacity: 0.8;
  margin-top: 5px;
}
.lyric-scroll {
  scrollbar-width: none;
}
.lyric-scroll::-webkit-scrollbar {
  display: none;
}
.lyric-line:focus-visible {
  outline: 2px solid var(--player-focus, var(--app-focus));
  outline-offset: 8px;
  border-radius: 6px;
}
.lyric-clicked {
  animation: lyric-pulse 0.65s ease-out;
}
@keyframes lyric-pulse {
  0% {
    background: var(--player-highlight, var(--app-selected));
    transform: scale(1.04);
  }
  100% {
    background: transparent;
    transform: scale(1);
  }
}
@media (prefers-reduced-motion: reduce) {
  .lyric-clicked {
    animation: none;
    background: var(--player-highlight, var(--app-selected));
  }
}
@media (max-width: 760px) {
  .lyric-scroll {
    --lyric-height: clamp(240px, 42svh, 400px);
  }
  .lyric-scroll li {
    font-size: 16px;
  }
  .lyric-scroll li.lyric-current {
    font-size: 21px;
  }
}
</style>

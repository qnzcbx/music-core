<script setup lang="ts">
import { isDesktop } from '../api/transport';
import { useHomeBackground } from '../features/home/background';
import { inject, ref, onUnmounted } from 'vue';
import { APPEARANCE, type Appearance } from '../appearance/theme';
import { useCoreClient } from '../composables/useCoreClient';
import { usePlayerVisuals } from '../composables/usePlayerTransition';
import DownloadSettings from '../components/DownloadSettings.vue';
import SearchBar from '../components/SearchBar.vue';
import PlayerLayoutSelector from '../components/PlayerLayoutSelector.vue';
const { background: homeBackground, selectBackground: selectHomeBackground } = useHomeBackground();
const appearance = inject<Appearance>(APPEARANCE)!;
const mode = ref(appearance.mode);
onUnmounted(
  appearance.subscribe(() => {
    mode.value = appearance.mode;
  }),
);
const {
  searchState: { sources, providers },
} = useCoreClient();
const {
  layout,
  lyricAlignment,
  selectLayout,
  selectLyricAlignment,
  phase,
  backgroundMode,
  selectBackground,
  ringPreset,
  selectRingPreset,
} = usePlayerVisuals();
</script>
<template>
  <section class="settings-view">
    <h1 class="page-title">设置</h1>
    <section>
      <h2>外观</h2>
      <h3>主题</h3>
      <fieldset aria-label="外观主题">
        <label
          v-for="choice in [
            ['light', '浅色'],
            ['dark', '深色'],
            ['system', '跟随系统'],
          ] as const"
          :key="choice[0]"
        >
          <input
            type="radio"
            name="settings-theme"
            :checked="mode === choice[0]"
            @change="appearance.select(choice[0])"
          />
          {{ choice[1] }}
        </label>
      </fieldset>
      <h3>首页背景</h3>
      <fieldset aria-label="首页背景">
        <label
          v-for="choice in [
            ['ink', '墨息'],
            ['voice', '弦外之音'],
          ] as const"
          :key="choice[0]"
        >
          <input
            type="radio"
            name="home-background"
            :checked="homeBackground === choice[0]"
            @change="selectHomeBackground(choice[0])"
          />
          {{ choice[1] }}
        </label>
      </fieldset>
      <h3>播放器样式</h3>
      <PlayerLayoutSelector
        inline
        :layout="layout"
        :alignment="lyricAlignment"
        :background="backgroundMode"
        :ring-preset="ringPreset"
        @background="selectBackground"
        @ring="selectRingPreset"
        :transitioning="phase !== 'idle'"
        @select="selectLayout"
        @align="selectLyricAlignment"
      />
    </section>

    <section>
      <h2>{{ isDesktop ? '下载与缓存' : '下载' }}</h2>
      <DownloadSettings />
    </section>
    <section>
      <h2>音乐来源</h2>
      <SearchBar
        v-model:sources="sources"
        :providers="providers"
      />
    </section>
  </section>
</template>
<style scoped>
.settings-view {
  min-width: 0;
  max-width: 780px;
  margin: 0;
  padding-bottom: 20px;
  text-align: left;
  --app-accent: var(--app-text);
  --app-link: var(--app-text);
  --app-focus: var(--app-text);
  --app-selected: color-mix(in srgb, var(--app-text) 9%, var(--app-surface-raised));
  --app-hover: color-mix(in srgb, var(--app-text) 5%, var(--app-surface-raised));
}
h1 {
  font-size: 26px;
  font-weight: 500;
  margin: 0 0 26px;
}
section > section {
  padding: 22px 0;
  border-top: 1px solid var(--app-border-soft);
}
h2 {
  font-size: 15px;
  margin: 0 0 16px;
}
fieldset {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  border: 0;
  padding: 0;
  margin: 0 0 20px;
}
label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  font-size: 13px;
}
fieldset > label {
  padding: 4px 12px;
  border: 1px solid var(--app-border-soft);
  border-radius: 8px;
  background: var(--app-surface-raised);
  cursor: pointer;
}
fieldset > label:has(input:checked) {
  background: var(--app-selected);
  border-color: var(--app-border-strong);
}
input {
  accent-color: var(--app-accent);
}
p {
  font-size: 12px;
  line-height: 1.9;
  color: var(--app-text-muted);
  max-width: 600px;
}
.settings-view :deep(.layout-panel) {
  left: 0;
  right: auto;
  max-width: calc(100vw - 40px);
}
.settings-view :deep(.preview-check) {
  background: var(--app-text);
  color: var(--app-surface-raised);
}
.settings-view :deep(.layout-current) {
  color: var(--app-text);
}
.settings-view :deep(.alignment-selected),
.settings-view :deep(.layout-card[aria-pressed='true']) {
  background: var(--app-selected);
  border-color: var(--app-border-strong);
}
.settings-view :deep(input) {
  accent-color: var(--app-text);
}
h3 {
  font-size: 13px;
  font-weight: 500;
  margin: 22px 0 12px;
}
</style>

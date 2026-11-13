<script setup lang="ts">
import StyleIcon from '~icons/lucide/shirt';
import PencilIcon from '~icons/lucide/pencil';
import BackIcon from '~icons/lucide/arrow-left';
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import {
  PLAYER_LAYOUTS,
  PLAYER_RING_PRESETS,
  type PlayerLayout,
  type LyricAlignment,
  type PlayerBackground,
  type RingPreset,
} from '../appearance/player-layout';

withDefaults(
  defineProps<{
    layout: PlayerLayout;
    alignment: LyricAlignment;
    background?: PlayerBackground;
    ringPreset?: RingPreset;
    transitioning?: boolean;
    inline?: boolean;
    iconOnly?: boolean;
    above?: boolean;
  }>(),
  { background: 'cover', ringPreset: 'smoky' },
);
const emit = defineEmits<{
  select: [layout: PlayerLayout];
  align: [alignment: LyricAlignment];
  background: [value: PlayerBackground];
  ring: [value: RingPreset];
  openChange: [open: boolean];
}>();
const panel = ref<HTMLDetailsElement>();
const editing = ref<PlayerLayout | null>(null);
const editingName = computed(() => PLAYER_LAYOUTS.find((item) => item.id === editing.value)?.name);
const backgrounds = [
  { id: 'cover', name: '跟随封面' },
  { id: 'light', name: '浅色' },
  { id: 'dark', name: '深色' },
] as const;
const rings = PLAYER_RING_PRESETS;
function close(restore = false) {
  if (!panel.value?.open) return;
  panel.value.open = false;
  editing.value = null;
  if (restore) panel.value.querySelector('summary')?.focus();
}
function toggled() {
  if (!panel.value?.open) editing.value = null;
  emit('openChange', !!panel.value?.open);
}
function select(layout: PlayerLayout) {
  close(true);
  emit('select', layout);
}
async function edit(layout: PlayerLayout) {
  emit('select', layout);
  editing.value = layout;
  await nextTick();
  panel.value?.querySelector<HTMLButtonElement>('.editor-back')?.focus();
}
async function back() {
  const previous = editing.value;
  editing.value = null;
  await nextTick();
  panel.value?.querySelector<HTMLButtonElement>(`[data-edit="${previous}"]`)?.focus();
}
function outside(event: PointerEvent) {
  if (!panel.value?.contains(event.target as Node)) close();
}
onMounted(() => document.addEventListener('pointerdown', outside));
onUnmounted(() => document.removeEventListener('pointerdown', outside));
</script>
<template>
  <component
    :is="inline ? 'section' : 'details'"
    ref="panel"
    class="layout-selector relative"
    :class="{ 'layout-inline': inline, 'layout-above': above }"
    @toggle="toggled"
    :aria-busy="transitioning"
    @keydown.esc.stop.prevent="close(true)"
  >
    <summary
      v-if="!inline"
      class="style-trigger"
      aria-label="播放器样式"
      title="播放器样式"
    >
      <StyleIcon aria-hidden="true" /><span v-if="!iconOnly">样式</span>
    </summary>
    <div
      class="layout-panel"
      :data-style-page="editing ? 'edit' : 'list'"
    >
      <template v-if="!editing">
        <h2
          v-if="!inline"
          class="layout-heading"
        >
          播放器样式
        </h2>
        <div
          class="layout-grid"
          role="group"
          aria-label="选择播放器样式"
        >
          <article
            v-for="item in PLAYER_LAYOUTS"
            :key="item.id"
            class="layout-card"
            :class="{ 'is-selected': layout === item.id }"
          >
            <button
              type="button"
              class="layout-select"
              :aria-label="item.name"
              :aria-pressed="layout === item.id"
              @click="select(item.id)"
            >
              <span
                class="layout-preview"
                :class="`preview-${item.id}`"
                aria-hidden="true"
              >
                <span class="preview-machine"
                  ><span class="preview-disc"><i /></span><span class="preview-arm"
                /></span>
                <span class="preview-copy"><i /><i /><i /><i /></span>
                <span
                  v-if="layout === item.id"
                  class="preview-check"
                  >✓</span
                >
              </span>
              <span class="layout-name">{{ item.name }}</span>
            </button>
            <button
              type="button"
              class="edit-layout"
              :data-edit="item.id"
              :aria-label="`编辑${item.name}`"
              @click="edit(item.id)"
            >
              <PencilIcon aria-hidden="true" />
            </button>
          </article>
        </div>
      </template>
      <template v-else>
        <header class="editor-heading">
          <button
            type="button"
            class="editor-back"
            aria-label="返回样式列表"
            @click="back"
          >
            <BackIcon aria-hidden="true" />
          </button>
          <h2>{{ editingName }}</h2>
        </header>
        <fieldset class="editor-section">
          <legend>背景</legend>
          <div class="background-options">
            <button
              v-for="item in backgrounds"
              :key="item.id"
              type="button"
              class="edit-choice"
              :aria-pressed="background === item.id"
              @click="emit('background', item.id)"
            >
              <i
                class="background-preview"
                :class="`background-${item.id}`"
                aria-hidden="true"
              />{{ item.name }}
            </button>
          </div>
        </fieldset>
        <fieldset class="editor-section">
          <legend>歌词对齐</legend>
          <div class="alignment-options">
            <button
              v-for="item in [
                { id: 'left', name: '居左' },
                { id: 'center', name: '居中' },
              ] as const"
              :key="item.id"
              type="button"
              class="edit-choice"
              :aria-pressed="alignment === item.id"
              @click="emit('align', item.id)"
            >
              <span
                class="alignment-preview"
                :class="item.id"
                aria-hidden="true"
                ><i /><i /><i /></span
              >{{ item.name }}
            </button>
          </div>
        </fieldset>
        <fieldset
          v-if="editing === 'vinyl-wide'"
          class="editor-section"
        >
          <legend>唱片颜色</legend>
          <div class="ring-options">
            <button
              v-for="item in rings"
              :key="item.id"
              type="button"
              class="edit-choice"
              :aria-pressed="ringPreset === item.id"
              @click="emit('ring', item.id)"
            >
              <i
                class="ring-swatch"
                :style="{ background: `linear-gradient(135deg,${item.colors})` }"
                aria-hidden="true"
              />{{ item.name
              }}<span
                v-if="ringPreset === item.id"
                aria-hidden="true"
                >✓</span
              >
            </button>
          </div>
        </fieldset>
      </template>
    </div>
  </component>
</template>
<style scoped>
.layout-selector {
  color: var(--player-control, var(--app-text));
  font-family: 'Microsoft YaHei UI', sans-serif;
}
.layout-selector summary {
  list-style: none;
  font: inherit;
  font-size: 12px;
}
.layout-selector summary::-webkit-details-marker {
  display: none;
}
.layout-panel {
  overflow: auto;
  scrollbar-width: thin;
  overscroll-behavior: contain;
}
.layout-name {
  display: block;
}
.layout-inline {
  color: var(--app-text);
  --player-text-muted: var(--app-text-muted);
  --player-focus: var(--app-focus);
  --player-border: var(--app-border);
}
.layout-inline .layout-panel {
  position: static;
  inset: auto;
  width: 100%;
  max-height: none;
  overflow: visible;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
.layout-inline .layout-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
@media (min-width: 700px) {
  .layout-inline .layout-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (min-width: 1100px) {
  .layout-inline .layout-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
.layout-preview {
  position: relative;
  display: block;
  height: 122px;
  overflow: hidden;
  border-radius: 7px;
  background: linear-gradient(
    120deg,
    var(--layout-preview-left, #e8eadb),
    var(--layout-preview-right, #f4e8e2)
  );
}
.preview-machine {
  position: absolute;
  width: 42%;
  aspect-ratio: 1;
  left: 8%;
  top: 16%;
  background: #fffffff0;
  border-radius: 12%;
  box-shadow: 3px 7px 10px #23382a15;
}
.preview-disc {
  position: absolute;
  inset: 12%;
  border-radius: 50%;
  background: repeating-radial-gradient(circle, #e1e9de44 0 1px, transparent 1px 3px), #42504b;
}
.preview-disc > i {
  position: absolute;
  inset: 23%;
  border-radius: 50%;
  background: color-mix(in srgb, var(--layout-preview-left, #d4b4b6) 80%, #9f747b);
}
.preview-arm {
  position: absolute;
  width: 4%;
  height: 60%;
  top: 2%;
  right: 8%;
  transform: rotate(18deg);
  background: #c2c8bb;
  border: 1px solid #8a9881;
  border-radius: 4px;
}
.preview-copy {
  position: absolute;
  top: 29%;
  right: 10%;
  width: 28%;
  display: grid;
  gap: 8px;
}
.preview-copy > i {
  display: block;
  height: 3px;
  border-radius: 2px;
  background: #3c514d45;
}
.preview-copy > i:first-child {
  background: #3c514d99;
  width: 80%;
  margin-bottom: 5px;
}
.preview-vinyl-wide .preview-machine {
  width: 64%;
  top: -56%;
  left: 54%;
  background: transparent;
  box-shadow: none;
}
.preview-vinyl-wide .preview-disc {
  inset: 0;
  background:
    repeating-radial-gradient(circle, #e6e6ed26 0 1px, transparent 1px 3px),
    conic-gradient(#aaaab0, #74747c, #bcbcc2, #92929b, #aaaab0);
}
.preview-vinyl-wide .preview-disc > i {
  inset: 19.8%;
}
.preview-vinyl-wide .preview-arm {
  display: none;
}
.preview-vinyl-wide .preview-copy {
  width: 31%;
  left: 9%;
  right: auto;
  top: 24%;
}
.preview-check {
  position: absolute;
  right: 8px;
  top: 8px;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #476b4b;
  color: #fbfff3;
  font: 12px sans-serif;
}
.preview-square-cover .preview-machine {
  left: 10%;
  top: 21%;
  width: 36%;
  border-radius: 4px;
  background: color-mix(in srgb, var(--layout-preview-left) 65%, #c5a69f);
}
.preview-square-cover .preview-disc,
.preview-square-cover .preview-arm {
  display: none;
}
.preview-lyrics-only .preview-machine {
  display: none;
}
.preview-lyrics-only .preview-copy {
  width: 48%;
  left: 26%;
  top: 23%;
}
.preview-lyrics-only .preview-copy > i:first-child {
  margin-inline: auto;
}

.layout-selector {
  --preview-height: 122px;
}
.style-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
}
.style-trigger:focus-visible,
button:focus-visible {
  outline: 2px solid var(--player-focus, var(--app-focus));
  outline-offset: 3px;
}
.layout-panel {
  position: fixed;
  z-index: 80;
  right: 24px;
  top: 88px;
  bottom: auto;
  width: min(390px, calc(100vw - 48px));
  margin: 0;
  padding: 22px;
  border: 1px solid var(--player-border, var(--app-border));
  border-radius: 16px;
  background: var(--player-surface, var(--app-surface-raised));
  color: var(--player-text, var(--app-text));
  box-shadow: var(--app-shadow-panel);
}
.layout-above .layout-panel {
  top: 88px;
  bottom: auto;
  max-height: calc(100dvh - var(--mini-player-height, 116px) - 112px);
}
.layout-heading {
  font-weight: 500;
  margin: 0 0 18px;
}
.layout-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.layout-card {
  position: relative;
  padding: 6px;
}
.layout-card.is-selected {
  border-color: var(--player-focus, var(--app-focus));
  background: color-mix(in srgb, var(--player-focus, var(--app-focus)) 12%, transparent);
}
.layout-select {
  display: block;
  width: 100%;
  border: 0;
  padding: 0;
  text-align: left;
  color: inherit;
  background: transparent;
  cursor: pointer;
}
.layout-preview {
  height: var(--preview-height);
}
.edit-layout {
  position: absolute;
  top: calc(var(--preview-height) - 30px);
  right: 12px;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid #ffffff80;
  border-radius: 8px;
  background: #fffdf8e8;
  color: #35434a;
  cursor: pointer;
  box-shadow: 0 2px 6px #0002;
}
.edit-layout svg,
.editor-back svg {
  width: 16px;
  height: 16px;
}
.editor-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 24px;
}
.editor-heading h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}
.editor-back {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 6px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.editor-section {
  border: 0;
  padding: 0;
  margin: 0 0 24px;
  min-width: 0;
}
.editor-section:last-child {
  margin-bottom: 0;
}
.editor-section legend {
  padding: 0;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--player-text-muted, var(--app-text-muted));
}
.background-options,
.alignment-options,
.ring-options {
  display: grid;
  gap: 8px;
}
.background-options {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.alignment-options {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.ring-options {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.edit-choice {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 9px;
  padding: 10px 5px;
  border: 1px solid var(--player-border, var(--app-border));
  border-radius: 10px;
  color: inherit;
  background: transparent;
  font-size: 12px;
  cursor: pointer;
}
.edit-choice[aria-pressed='true'] {
  border-color: var(--player-focus, var(--app-focus));
  background: color-mix(in srgb, var(--player-focus, var(--app-focus)) 12%, transparent);
}
.background-preview {
  width: 100%;
  height: 38px;
  border-radius: 5px;
}
.background-cover {
  background: linear-gradient(
    130deg,
    var(--layout-preview-left, #e8e4d5),
    var(--layout-preview-right, #d4e4ea)
  );
}
.background-light {
  background: #f5f4ef;
  border: 1px solid #e2e0da;
}
.background-dark {
  background: #151b20;
}
.alignment-preview {
  display: grid;
  gap: 5px;
  width: 70%;
  height: 38px;
  align-content: center;
}
.alignment-preview i {
  display: block;
  height: 3px;
  width: 100%;
  background: currentColor;
  opacity: 0.55;
  border-radius: 2px;
}
.alignment-preview i:nth-child(2) {
  width: 70%;
}
.alignment-preview i:last-child {
  width: 85%;
}
.alignment-preview.center i {
  margin-inline: auto;
}
.ring-swatch {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid #0002;
}
@media (max-width: 600px) {
  .layout-selector {
    --preview-height: 86px;
  }
  .layout-panel,
  .layout-above .layout-panel {
    top: auto;
    bottom: calc(var(--mini-player-height, 160px) + 14px);
    left: 12px;
    right: 12px;
    width: auto;
    max-height: calc(100dvh - var(--mini-player-height, 160px) - 46px);
    padding: 18px;
    border-radius: 18px;
  }
}
.layout-inline .layout-panel {
  position: static;
  width: 100%;
  max-height: none;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.layout-panel .edit-choice {
  color: var(--player-text, var(--app-text));
  border: 1px solid var(--player-border, var(--app-border));
}
.layout-panel .edit-choice[aria-pressed='true'] {
  border-color: var(--player-focus, var(--app-focus));
}
.layout-panel .editor-back {
  color: var(--player-text, var(--app-text));
}
.layout-panel .edit-layout {
  color: #35434a;
  background: #fffdf8e8;
  border: 1px solid #ffffff80;
}
.layout-panel .layout-card.is-selected {
  border-color: var(--player-focus, var(--app-focus));
}

/* 列表与编辑共用稳定的侧栏尺寸；内容少时也保留呼吸空间。 */
.layout-selector:not(.layout-inline) .layout-panel {
  top: 16px;
  right: 16px;
  bottom: auto;
  width: min(510px, max(480px, 38vw), calc(100vw - 32px));
  height: calc(100dvh - var(--mini-player-height, 116px) - 32px);
  max-height: calc(100dvh - var(--mini-player-height, 116px) - 32px);
  padding: 16px;
  border-radius: 12px;
  background: var(--player-panel-bg, var(--app-surface-raised));
}
.layout-heading {
  font-size: 18px;
  margin: 0 0 20px;
  line-height: 1.5;
}
.layout-grid {
  column-gap: 8px;
  row-gap: 8px;
}
.layout-panel .layout-card {
  padding: 0;
  border: 1px solid transparent;
  border-radius: 7px;
}
.layout-panel .layout-card.is-selected {
  background: transparent;
  border-color: transparent;
}
.layout-preview {
  height: auto;
  aspect-ratio: 1.84;
  border-radius: 5px;
}
.layout-name {
  padding: 10px 0 0;
  font-size: 14px;
  line-height: 1.5;
}
.edit-layout {
  top: auto;
  bottom: 39px;
  right: 9px;
  border-radius: 50%;
}
.preview-check {
  width: 25px;
  height: 25px;
  background: #19ca71;
  color: #10241a;
  font-weight: 600;
}
.editor-heading {
  justify-content: flex-start;
  gap: 5px;
  padding: 0;
  margin: 0 0 32px;
  border: 0;
}
.editor-heading h2 {
  font-size: 18px;
  line-height: 1.5;
}
.editor-back {
  margin-left: -6px;
}
.editor-section {
  margin-bottom: 34px;
}
.editor-section legend {
  margin-bottom: 18px;
  font-size: 15px;
  color: var(--player-text, var(--app-text));
}
.background-options {
  display: flex;
  justify-content: flex-start;
  gap: 16px;
}
.background-options .edit-choice {
  flex: 0 0 80px;
  padding: 4px;
  border-color: transparent;
  background: transparent;
}
.background-preview {
  width: 32px;
  height: 32px;
  border-radius: 6px;
}
.background-options .edit-choice[aria-pressed='true'] .background-preview {
  outline: 2px solid #19ca71;
  outline-offset: 3px;
}
.alignment-options {
  gap: 12px;
}
.alignment-options .edit-choice {
  align-items: stretch;
  text-align: left;
  border: 0;
  padding: 0;
  background: transparent;
  position: relative;
}
.alignment-preview {
  width: 100%;
  height: 110px;
  padding: 28px 20px;
  border-radius: 5px;
  background: linear-gradient(
    130deg,
    var(--layout-preview-left, #e7e7de),
    var(--layout-preview-right, #dee8eb)
  );
  color: #46535d;
}
.alignment-preview i {
  width: 75%;
  height: 3px;
}
.alignment-preview i:nth-child(2) {
  width: 50%;
}
.alignment-preview i:last-child {
  width: 65%;
}
.alignment-options .edit-choice[aria-pressed='true']::after {
  content: '✓';
  position: absolute;
  right: 10px;
  top: 10px;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #19ca71;
  color: #10241a;
}
.ring-options {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
}
.ring-options .edit-choice {
  border-color: transparent;
  background: transparent;
  padding: 4px;
  position: relative;
}
.ring-options .edit-choice[aria-pressed='true'] .ring-swatch {
  outline: 2px solid #19ca71;
  outline-offset: 3px;
}
.ring-options .edit-choice > span {
  position: absolute;
  right: 9px;
  top: 27px;
  color: #fff;
  text-shadow: 0 1px 3px #000;
}
.layout-panel .background-options .edit-choice[aria-pressed='true'],
.layout-panel .ring-options .edit-choice[aria-pressed='true'] {
  border-color: transparent;
  background: transparent;
}
@media (max-width: 600px) {
  .layout-selector:not(.layout-inline) .layout-panel {
    top: auto;
    right: 12px;
    left: 12px;
    bottom: calc(var(--mini-player-height, 160px) + 14px);
    width: auto;
    height: calc(100dvh - var(--mini-player-height, 160px) - 68px);
    max-height: calc(100dvh - var(--mini-player-height, 160px) - 68px);
    padding: 12px;
    border-radius: 16px;
  }
  .layout-grid {
    gap: 4px 4px;
  }
  .layout-name {
    font-size: 13px;
  }
  .editor-section {
    margin-bottom: 28px;
  }
  .alignment-preview {
    height: 84px;
    padding: 24px 12px;
  }
  .ring-options {
    gap: 8px;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>

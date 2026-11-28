<script setup lang="ts">
import StyleIcon from '~icons/lucide/shirt';
import PencilIcon from '~icons/lucide/pencil';
import CloseIcon from '~icons/lucide/x';
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogClose,
} from 'reka-ui';
import { computed, onMounted, onUnmounted, ref } from 'vue';
import {
  PLAYER_LAYOUTS,
  PLAYER_RING_PRESETS,
  type PlayerLayout,
  type LyricAlignment,
  type PlayerBackground,
  type RingPreset,
} from '../appearance/player-layout';

const props = withDefaults(
  defineProps<{
    layout: PlayerLayout;
    alignments: Readonly<Record<PlayerLayout, LyricAlignment>>;
    backgrounds: Readonly<Record<PlayerLayout, PlayerBackground>>;
    ringPreset?: RingPreset;
    transitioning?: boolean;
    inline?: boolean;
    iconOnly?: boolean;
    above?: boolean;
  }>(),
  { ringPreset: 'smoky' },
);
const emit = defineEmits<{
  select: [layout: PlayerLayout];
  align: [alignment: LyricAlignment, layout: PlayerLayout];
  background: [value: PlayerBackground, layout: PlayerLayout];
  ring: [value: RingPreset];
  openChange: [open: boolean];
}>();
const panel = ref<HTMLDetailsElement>();
const editing = ref<PlayerLayout>('classic');
const editorOpen = ref(false);
let editTrigger: HTMLButtonElement | undefined;
const background = computed(() => props.backgrounds[editing.value]);
const alignment = computed(() => props.alignments[editing.value]);
const editingName = computed(() => PLAYER_LAYOUTS.find((item) => item.id === editing.value)?.name);
const backgroundOptions = [
  { id: 'cover', name: '跟随封面' },
  { id: 'light', name: '浅色' },
  { id: 'dark', name: '深色' },
] as const;
const rings = PLAYER_RING_PRESETS;
const backgroundName = computed(
  () => backgroundOptions.find((item) => item.id === background.value)?.name,
);
const ringName = computed(() => rings.find((item) => item.id === props.ringPreset)?.name);
function close(restore = false) {
  if (!panel.value?.open) return;
  panel.value.open = false;
  if (restore) panel.value.querySelector('summary')?.focus();
}
function toggled() {
  emit('openChange', !!panel.value?.open);
}
function select(layout: PlayerLayout) {
  close(true);
  emit('select', layout);
}
function edit(layout: PlayerLayout, event: MouseEvent) {
  editTrigger = event.currentTarget as HTMLButtonElement;
  editing.value = layout;
  editorOpen.value = true;
}
function restoreFocus(event: Event) {
  event.preventDefault();
  editTrigger?.focus({ preventScroll: true });
}
function outside(event: PointerEvent) {
  if (!editorOpen.value && !panel.value?.contains(event.target as Node)) close();
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
      <StyleIcon aria-hidden="true" />
      <span v-if="!iconOnly">样式</span>
    </summary>
    <div class="layout-panel">
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
              class="layout-preview alignment-scene"
              :class="[
                `preview-${item.id}`,
                `align-${alignments[item.id]}`,
              ]"
              aria-hidden="true"
            >
              <span class="preview-machine">
                <span class="preview-disc"><i /></span>
                <span class="preview-arm" />
              </span>
              <span class="preview-copy"><i /><i /><i /><i /><i /></span>
              <span
                v-if="layout === item.id"
                class="preview-check"
              >
                ✓
              </span>
            </span>
            <span class="layout-name">{{ item.name }}</span>
          </button>
          <button
            type="button"
            class="edit-layout"
            :data-edit="item.id"
            :aria-label="`编辑${item.name}`"
            @click.stop="edit(item.id, $event)"
          >
            <PencilIcon aria-hidden="true" />
          </button>
        </article>
      </div>
    </div>
    <DialogRoot v-model:open="editorOpen">
      <DialogPortal>
        <DialogOverlay class="editor-overlay" />
        <DialogContent
          class="editor-dialog"
          :aria-describedby="undefined"
          @close-auto-focus="restoreFocus"
        >
          <header class="editor-heading">
            <DialogTitle>{{ editingName }}</DialogTitle>
            <DialogClose class="editor-close" aria-label="关闭">
              <CloseIcon aria-hidden="true" />
            </DialogClose>
          </header>
          <fieldset class="editor-section">
            <legend>
              背景
              <span
                class="selected-option"
                aria-live="polite"
              >
                已选{{ backgroundName }}
              </span>
            </legend>
            <div class="background-options">
              <button
                v-for="item in backgroundOptions"
                :key="item.id"
                type="button"
                class="edit-choice"
                :aria-pressed="background === item.id"
                :aria-label="item.name"
                :title="item.name"
                @click="emit('background', item.id, editing)"
              >
                <i
                  class="background-preview"
                  :class="`background-${item.id}`"
                  aria-hidden="true"
                />
              </button>
            </div>
          </fieldset>
          <fieldset
            v-if="editing === 'vinyl-wide'"
            class="editor-section"
          >
            <legend>
              唱片颜色
              <span
                class="selected-option"
                aria-live="polite"
              >
                已选{{ ringName }}
              </span>
            </legend>
            <div class="ring-options">
              <button
                v-for="item in rings"
                :key="item.id"
                type="button"
                class="edit-choice"
                :aria-pressed="ringPreset === item.id"
                :aria-label="item.name"
                :title="item.name"
                @click="emit('ring', item.id)"
              >
                <i
                  class="ring-swatch"
                  :style="{ background: `linear-gradient(135deg,${item.colors})` }"
                  aria-hidden="true"
                />
              </button>
            </div>
          </fieldset>
          <fieldset class="editor-section">
            <legend>封面和歌词版式</legend>
            <div class="alignment-options">
              <button
                v-for="item in [
                  { id: 'left', name: '居左' },
                  { id: 'center', name: '居中' },
                ] as const"
                :key="item.id"
                type="button"
                class="edit-choice alignment-choice"
                :aria-label="`歌词${item.name}`"
                :aria-pressed="alignment === item.id"
                @click="emit('align', item.id, editing)"
              >
                <span
                  class="alignment-scene layout-preview"
                  :class="[`preview-${editing}`, `align-${item.id}`]"
                  aria-hidden="true"
                >
                  <span class="preview-machine">
                    <span class="preview-disc"><i /></span>
                    <span class="preview-arm" />
                  </span>
                  <span class="preview-copy"><i /><i /><i /><i /><i /></span>
                  <span
                    v-if="alignment === item.id"
                    class="preview-check"
                  >
                    ✓
                  </span>
                </span>
                <span>歌词{{ item.name }}</span>
              </button>
            </div>
          </fieldset>
        </DialogContent>
      </DialogPortal>
    </DialogRoot>
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
.editor-close svg {
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
.editor-close {
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
.layout-panel .edit-layout {
  color: #35434a;
  background: #fffdf8e8;
  border: 1px solid #ffffff80;
}
.layout-panel .layout-card.is-selected {
  border-color: var(--player-focus, var(--app-focus));
}

/* 播放器中的样式列表使用固定的侧栏尺寸。 */
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

<style scoped>
.alignment-choice {
  padding: 0;
  border: 0;
  background: transparent;
  align-items: stretch;
  text-align: left;
}
.alignment-choice[aria-pressed='true'] {
  background: transparent;
}
.alignment-scene {
  width: 100%;
  height: auto;
  aspect-ratio: 1.85;
  border: 1px solid transparent;
  border-radius: 10px;
}
.alignment-choice[aria-pressed='true'] .alignment-scene {
  border-color: #18bd69;
  box-shadow: inset 0 0 0 1px #18bd6922;
}
.alignment-choice > span:last-child {
  padding: 0 2px;
}
.alignment-scene .preview-machine {
  width: 24%;
  left: 6%;
  top: 34%;
  aspect-ratio: 456/429;
  background: linear-gradient(135deg, #fff, #e8eae7);
  box-shadow: 1px 3px 5px #26353320;
}
.alignment-scene .preview-disc {
  inset: auto;
  width: 75.44%;
  aspect-ratio: 1;
  left: 12.28%;
  top: 9.8%;
  background: conic-gradient(#85929f, #657281, #b2bdc8, #85929f);
  box-shadow: 0 0 0 2px #aeb4b644;
}
.alignment-scene .preview-disc > i {
  inset: 20%;
  background: #386380;
  box-shadow: 0 0 0 1px #344455;
}
.alignment-scene .preview-arm {
  height: 72%;
  width: 3%;
  right: 9%;
  top: 4%;
  transform: rotate(8deg);
  background: #edf0ed;
  border-color: #9ba5a2;
  border-radius: 1px 1px 60% 0;
}
.alignment-scene .preview-copy {
  width: 57%;
  right: 6%;
  top: 37%;
  gap: 5px;
}
.alignment-scene .preview-copy > i {
  width: 92%;
  height: 3px;
  opacity: 0.55;
  margin: 0;
  background: #63728e;
}
.alignment-scene .preview-copy > i:first-child {
  width: 58%;
  height: 4px;
  background: #303e53;
  opacity: 1;
}
.alignment-scene .preview-copy > i:nth-child(2) {
  width: 42%;
  height: 2px;
  margin-bottom: 5px;
}
.alignment-scene .preview-copy > i:nth-child(3) {
  width: 100%;
  background: #5376b1;
  opacity: 1;
}
.alignment-scene .preview-copy > i:nth-child(4) {
  width: 84%;
}
.alignment-scene.align-center .preview-copy > i {
  margin-inline: auto;
}
.alignment-scene.preview-vinyl-wide .preview-machine {
  width: 62%;
  left: 59%;
  top: -39%;
  background: transparent;
  box-shadow: none;
  aspect-ratio: 1;
}
.alignment-scene.preview-vinyl-wide .preview-disc {
  inset: 0;
  width: 100%;
  background: conic-gradient(#b0aab7, #777381, #bec0cd, #9992a3, #b0aab7);
}
.alignment-scene.preview-vinyl-wide .preview-disc > i {
  inset: 19.8%;
}
.alignment-scene.preview-vinyl-wide .preview-copy {
  left: 8%;
  right: auto;
  top: 38%;
  width: 47%;
}
.alignment-scene.preview-square-cover .preview-machine {
  width: 27%;
  aspect-ratio: 1;
  left: 6%;
  top: 30%;
  border-radius: 3px;
  background: linear-gradient(145deg, #779aa9, #bcb6c1 50%, #d9c0a7);
}
.alignment-scene.preview-lyrics-only .preview-copy {
  width: 70%;
  left: 15%;
  top: 31%;
}
.alignment-scene .preview-check {
  width: 17px;
  height: 17px;
  right: 7px;
  top: 7px;
  font-size: 10px;
  background: #18bd69;
}
</style>

<style scoped>
/* 各分组选项从同一左边线开始，不因缩略图类型产生额外缩进。 */
.background-options .edit-choice,
.ring-options .edit-choice {
  align-items: flex-start;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
}
.background-options .background-preview {
  width: 40px;
  height: 40px;
  aspect-ratio: 1;
}
.ring-options .edit-choice {
  align-items: center;
  text-align: center;
}
.background-options .edit-choice[aria-pressed='true'] .background-preview,
.ring-options .edit-choice[aria-pressed='true'] .ring-swatch {
  outline: 2px solid #18bd69;
  outline-offset: -2px;
}
.alignment-choice > span:last-child {
  padding-inline: 0;
}
</style>

<style scoped>
.alignment-scene .preview-copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.alignment-scene.align-center .preview-copy {
  align-items: center;
}
.alignment-scene .preview-copy > i {
  flex-shrink: 0;
}
.alignment-scene.align-left .preview-copy > i {
  margin-inline: 0;
}
.alignment-options .alignment-choice[aria-pressed='true']::after {
  content: none;
}
</style>

<style scoped>
.background-options,
.ring-options {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}
.background-options .edit-choice,
.ring-options .edit-choice {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
}
.ring-options .ring-swatch {
  width: 40px;
  height: 40px;
  border-radius: 5px;
}
.layout-card .alignment-scene {
  height: auto;
  aspect-ratio: 1.85;
}
</style>

<style scoped>
.selected-option {
  margin-left: 8px;
  padding-left: 8px;
  border-left: 1px solid var(--player-border, var(--app-border));
  font-size: 0.9em;
  font-weight: 400;
  color: var(--player-text-muted, var(--app-text-muted));
}
</style>

<style scoped>
.editor-overlay {
  position: fixed;
  inset: 0;
  z-index: 110;
  background: #0006;
  animation: editor-fade 180ms ease both;
}
.editor-dialog {
  position: fixed;
  inset: 50% auto auto 50%;
  z-index: 111;
  translate: -50% -50%;
  width: min(760px, calc(100% - 32px));
  max-height: calc(100dvh - 32px);
  box-sizing: border-box;
  overflow: auto;
  overscroll-behavior: contain;
  padding: clamp(16px, 4vw, 26px);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: var(--app-surface);
  color: var(--app-text);
  box-shadow: 0 20px 80px #0004;
  animation: editor-enter 180ms ease both;
}
.editor-dialog .editor-heading {
  justify-content: space-between;
  margin: 0 0 16px;
}
.editor-close {
  flex-shrink: 0;
  border-radius: 8px;
}
.editor-close:hover {
  background: var(--app-hover);
}
.editor-dialog .editor-section {
  margin-bottom: 18px;
}
.editor-dialog .editor-section:last-child {
  margin-bottom: 0;
}
.editor-dialog .editor-section legend {
  margin-bottom: 10px;
}
.editor-overlay[data-state='closed'] {
  animation: editor-fade-out 180ms ease both;
}
.editor-dialog[data-state='closed'] {
  animation: editor-exit 180ms ease both;
}
@keyframes editor-fade { from { opacity: 0; } }
@keyframes editor-fade-out { to { opacity: 0; } }
@keyframes editor-enter { from { opacity: 0; scale: 0.98; } }
@keyframes editor-exit { to { opacity: 0; scale: 0.98; } }
@media (prefers-reduced-motion: reduce) {
  .editor-overlay[data-state],
  .editor-dialog[data-state] { animation: none; }
}
</style>

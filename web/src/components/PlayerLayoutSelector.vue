<script setup lang="ts">
import StyleIcon from '~icons/lucide/shirt';
import { onMounted, onUnmounted, ref, useId } from "vue";
import { PLAYER_LAYOUTS, type PlayerLayout, type LyricAlignment } from "../appearance/player-layout";
defineProps<{ layout: PlayerLayout; alignment: LyricAlignment; transitioning?: boolean; inline?: boolean; iconOnly?:boolean; above?:boolean }>();
const emit = defineEmits<{ select: [layout: PlayerLayout]; align: [alignment: LyricAlignment]; openChange:[open:boolean] }>();
const alignmentGroup = `player-lyric-alignment-${useId()}`;
const panel = ref<HTMLDetailsElement>();
function close(restore = false) {
  if (!panel.value?.open) return;
  panel.value.open = false;
  if (restore) panel.value.querySelector("summary")?.focus();
}
function select(layout: PlayerLayout) {
  close(true);
  emit("select", layout);
}
function outside(event: PointerEvent) {
  if (!panel.value?.contains(event.target as Node)) close();
}
onMounted(() => document.addEventListener("pointerdown", outside));
onUnmounted(() => document.removeEventListener("pointerdown", outside));
</script>
<template>
  <component :is="inline ? 'section' : 'details'" ref="panel" class="layout-selector relative" :class="{'layout-inline':inline,'layout-above':above}" @toggle="emit('openChange',!!panel?.open)" :aria-busy="transitioning" @keydown.esc.stop.prevent="close(true)">
    <summary
      v-if="!inline"
      class="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-solid border-app-border bg-transparent px-3 py-2 text-xs text-app-muted hover:bg-app-surface focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-app-focus"
      aria-label="播放器样式" title="播放器样式"
    >
      <StyleIcon aria-hidden="true"/><span v-if="!iconOnly">样式</span>
    </summary>
    <div
      class="layout-panel absolute right-0 z-50 mt-2 rounded-xl border border-solid border-app-border bg-app-raised p-4 shadow-app-panel"
    >
      <p v-if="!inline" class="layout-heading">播放器样式 <span>让音乐换一种呈现</span></p>
      <div 
        class="layout-grid grid grid-cols-2 gap-3" 
        role="group" 
        aria-label="选择播放器样式"
      >
        <button
          v-for="item in PLAYER_LAYOUTS"
          :key="item.id"
          type="button"
          class="layout-card"
          :aria-label="item.name"
          :aria-pressed="layout === item.id"
          @click="select(item.id)"
        >
          <span class="layout-preview" :class="`preview-${item.id}`" aria-hidden="true">
            <span class="preview-machine"
              ><span class="preview-disc"><i /></span><span class="preview-arm"
            /></span>
            <span class="preview-copy"><i /><i /><i /><i /></span>
            <span v-if="layout === item.id" class="preview-check">✓</span>
          </span>
          <span class="layout-name"
            >{{ item.name }}<span v-if="layout === item.id" class="layout-current">当前</span></span
          >
          <span class="layout-description">{{ item.description }}</span>
        </button>
      </div>
      <fieldset class="alignment-settings">
        <legend>歌词对齐 <span>仅用于当前样式</span></legend>
        <div class="grid grid-cols-2 gap-3">
          <label v-for="choice in ([{id:'left',label:'居左',icon:'☰'}, {id:'center',label:'居中',icon:'≡'}] as const)" :key="choice.id" class="alignment-choice" :class="{'alignment-selected': alignment === choice.id}">
            <input type="radio" :name="alignmentGroup" :value="choice.id" :checked="alignment === choice.id" @change="emit('align', choice.id)" />
            <span aria-hidden="true">{{ choice.icon }}</span>{{ choice.label }}
          </label>
        </div>
      </fieldset>
    </div>
  </component>
</template>
<style scoped>
.layout-selector {
  color: var(--player-control);
  font-family: "Microsoft YaHei UI", sans-serif;
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
  scrollbar-width: none;
  -ms-overflow-style: none;
  width: min(540px, calc(100vw - 36px));
  max-height: calc(100dvh - var(--mini-player-height, 116px) - 90px);
  overflow: auto;
}
.layout-panel::-webkit-scrollbar { display: none; width: 0; height: 0; }
.layout-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 14px;
  font-size: 15px;
}
.layout-heading > span {
  color: var(--player-text-muted);
  font-size: 10px;
}
.layout-card {
  display: block;
  min-width: 0;
  padding: 6px;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.layout-card:hover {
  background: #e3e9de80;
}
.layout-card[aria-pressed="true"] {
  border-color: var(--player-focus);
  background: #e3e9de66;
}
.layout-card:focus-visible {
  outline: 2px solid var(--player-focus);
  outline-offset: 2px;
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
.layout-name {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 10px 1px 5px;
  font-size: 13px;
}
.layout-current {
  color: #476b4b;
  font-size: 10px;
}
.layout-description {
  display: block;
  color: var(--player-text-muted);
  font-size: 10px;
  line-height: 1.6;
}
.preview-square-cover .preview-machine { left: 10%; top: 21%; width: 36%; border-radius: 4px; background: color-mix(in srgb,var(--layout-preview-left) 65%,#c5a69f); }
.preview-square-cover .preview-disc, .preview-square-cover .preview-arm { display: none; }
.preview-lyrics-only .preview-machine { display: none; }
.preview-lyrics-only .preview-copy { width: 48%; left: 26%; top: 23%; }
.preview-lyrics-only .preview-copy > i:first-child { margin-inline: auto; }
.alignment-settings { margin: 16px 0 0; padding: 12px 0 0; border: 0; border-top: 1px solid var(--player-border); min-width: 0; }
.alignment-settings legend { padding: 0 0 8px; font-size: 12px; }
.alignment-settings legend span { margin-left: 8px; color: var(--player-text-muted); font-size: 10px; }
.alignment-choice { display: flex; align-items: center; justify-content: center; gap: 9px; padding: 10px 8px; border: 1px solid var(--player-border); border-radius: 8px; font-size: 12px; cursor: pointer; }
.alignment-choice input { width: 14px; height: 14px; margin: 0; accent-color: var(--player-focus); }
.alignment-choice:focus-within { outline: 2px solid var(--player-focus); outline-offset: 2px; }
.alignment-choice:hover, .alignment-selected { background: #e3e9de80; }
@media (max-width: 600px) {
  .layout-preview {
    height: 76px;
  }
  .layout-panel {
    position: fixed;
    left: 18px;
    right: 18px;
    top: 62px;
    margin-top: 0;
    width: auto;
    padding: 12px;
  }
  .layout-heading > span {
    display: none;
  }
}
.layout-selector summary svg{width:19px;height:19px}.layout-above .layout-panel{top:auto;bottom:calc(100% + 16px);margin:0;max-height:calc(100dvh - 220px)}@media(max-width:600px){.layout-above .layout-panel{top:auto;bottom:190px;max-height:calc(100dvh - 240px)}}
</style>
<style scoped>
.layout-inline{color:var(--app-text);--player-text-muted:var(--app-text-muted);--player-focus:var(--app-focus);--player-border:var(--app-border);}
.layout-inline .layout-panel{position:static;inset:auto;width:100%;max-width:none;max-height:none;overflow:visible;margin:0;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none;}
.layout-inline .layout-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}
.layout-inline .layout-name{flex-wrap:wrap;gap:4px;}
@media(min-width:700px){.layout-inline .layout-grid{grid-template-columns:repeat(3,minmax(0,1fr));}}
@media(min-width:1100px){.layout-inline .layout-grid{grid-template-columns:repeat(4,minmax(0,1fr));}}
</style>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
const props = defineProps<{ anchor: HTMLElement; label: string; kind: string }>();
const emit = defineEmits<{ close: [restoreFocus?: boolean] }>();
const panel = ref<HTMLElement>();
const position = ref({ left: '8px', top: '8px', visibility: 'hidden' as 'hidden' | 'visible' });
function place() {
  const element = panel.value;
  if (!element || !props.anchor.isConnected) return;
  const a = props.anchor.getBoundingClientRect(), b = element.getBoundingClientRect();
  position.value = { left: `${Math.max(8, Math.min(innerWidth - b.width - 8, a.x + a.width / 2 - b.width / 2))}px`,
    top: `${Math.max(8, Math.min(innerHeight - b.height - 8, a.top - b.height - 12))}px`, visibility: 'visible' };
}
function outside(event: PointerEvent) {
  if (!panel.value?.contains(event.target as Node) && !props.anchor.contains(event.target as Node)) emit('close', false);
}
function key(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); emit('close', true); }
  // A nonmodal popover lets Tab continue through the page without trapping focus.
  if (event.key === 'Tab') setTimeout(() => {
    if (panel.value && !panel.value.contains(document.activeElement)) emit('close', false);
  }, 0);
}
function scroll(event: Event) { if (!panel.value?.contains(event.target as Node)) emit('close', false); }
const route = useRoute();
watch(() => route.fullPath, () => emit('close', false));
let observer: ResizeObserver | undefined;
let disposed = false;
onMounted(async () => {
  await nextTick(); if (disposed) return;
  place(); await nextTick(); if (disposed) return;
  panel.value?.querySelector<HTMLElement>('[aria-checked="true"],input,button,select,summary')?.focus({ preventScroll: true });
  document.addEventListener('pointerdown', outside); document.addEventListener('keydown', key);
  window.addEventListener('resize', place); window.addEventListener('scroll', scroll, true);
  observer = new ResizeObserver(place); observer.observe(panel.value!);
  const footer = props.anchor.closest('.player'); if (footer) observer.observe(footer);
});
onUnmounted(() => {
  disposed = true;
  observer?.disconnect(); document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', key);
  window.removeEventListener('resize', place); window.removeEventListener('scroll', scroll, true);
});
</script>
<template>
  <Teleport to="body">
    <section ref="panel" class="player-popover" :class="`popover-${kind}`" :style="position" :aria-label="label" role="dialog" :id="`player-${kind}-popover`" tabindex="-1"><slot /></section>
  </Teleport>
</template>
<style>
.player-popover { position:fixed; z-index:60; box-sizing:border-box; max-width:calc(100vw - 16px); max-height:calc(100dvh - 16px); overflow:auto; border:1px solid var(--app-border-soft); border-radius:14px; background:var(--app-surface-raised); color:var(--app-text); box-shadow:0 8px 28px var(--app-shadow-color); padding:8px; }
.player-popover button { color:inherit; background:transparent; border:0; cursor:pointer; border-radius:8px; }
.player-popover button:hover { background:var(--app-hover); }
.player-popover button:disabled { opacity:.45; cursor:default; }
.player-popover :is(button,input,select,summary):focus-visible { outline:2px solid var(--app-link); outline-offset:2px; }
.player-popover svg { width:18px; height:18px; flex-shrink:0; }
</style>

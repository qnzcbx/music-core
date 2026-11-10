<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import SlidersIcon from '~icons/lucide/sliders-horizontal';
import ChevronIcon from '~icons/lucide/chevron-down';
import SearchBar from '../SearchBar.vue';
import { useCoreClient } from '../../composables/useCoreClient';
import { primarySources, orderedSources } from '../../config/source-profile';
const { searchState: { sources, providers } } = useCoreClient();
const selected = computed(() => orderedSources(providers.value).filter(p => sources.value.includes(p.id)));
const summary = computed(() => `来源：${selected.value[0]?.name ?? '未选择'}${selected.value.length > 1 ? ` +${selected.value.length-1}` : ''}`);
const hasResearch = computed(() => orderedSources(providers.value).some(p => p.capabilities.search && !primarySources(providers.value).some(row => row.id === p.id)));
const compact = ref(true), opened = ref(false), host = ref<HTMLElement>(), button = ref<HTMLButtonElement>(), panel = ref<HTMLElement>();
const position = ref({ left:'12px', top:'72px', width:'360px' });
let observer: ResizeObserver | undefined;
function close(restore = false) { opened.value = false; if (restore) button.value?.focus(); }
async function toggle() {
  if (opened.value) { close(); return; }
  const box = button.value!.getBoundingClientRect(), width = Math.min(380, innerWidth-24);
  position.value = { left:`${Math.max(12,Math.min(box.right-width,innerWidth-width-12))}px`, top:`${box.bottom+8}px`, width:`${width}px` };
  opened.value = true; await nextTick(); panel.value?.querySelector<HTMLInputElement>('input:not(:disabled)')?.focus();
}
function outside(event: PointerEvent) { if (!host.value?.contains(event.target as Node) && !panel.value?.contains(event.target as Node)) close(); }
function scrolled(event: Event) { if (!panel.value?.contains(event.target as Node)) close(); }
onMounted(() => {
  const topbar = host.value!.closest('.app-topbar')!;
  observer = new ResizeObserver(() => { const value = topbar.clientWidth < 1100; if (value !== compact.value) { close(); compact.value = value; } });
  observer.observe(topbar);
  document.addEventListener('pointerdown', outside); document.addEventListener('scroll', scrolled, true);
});
onUnmounted(() => { observer?.disconnect(); document.removeEventListener('pointerdown', outside); document.removeEventListener('scroll', scrolled, true); });
</script>
<template>
  <div ref="host" class="source-selector" :data-compact="compact">
    <SearchBar v-if="!compact" v-model:sources="sources" :providers="providers" primary-only />
    <button v-if="compact || hasResearch" ref="button" type="button" class="source-trigger" :aria-label="compact ? summary : '更多来源'" :title="compact ? summary : '更多来源'" :aria-expanded="opened" aria-controls="source-selection-panel" @click="toggle" @keydown.esc.stop.prevent="close(true)">
      <SlidersIcon v-if="compact" aria-hidden="true" /><span>{{ compact ? summary : '更多来源' }}</span><ChevronIcon aria-hidden="true" />
    </button>
    <Teleport to="body">
      <section v-if="opened" id="source-selection-panel" ref="panel" class="source-panel" aria-label="选择音乐来源" :style="position" @keydown.esc.stop.prevent="close(true)">
        <h2>{{ compact ? '音乐来源' : '更多来源' }}</h2>
        <SearchBar v-model:sources="sources" :providers="providers" :research-only="!compact" />
        <p>至少选择一个来源。更改后点击「更新搜索」应用。</p>
      </section>
    </Teleport>
  </div>
</template>
<style scoped>
.source-selector { display:flex; align-items:center; gap:8px; min-width:0; }
.source-selector :deep(.primary-sources) { flex-wrap:nowrap; }
.source-trigger { display:flex; align-items:center; gap:6px; flex-shrink:0; max-width:100%; height:36px; padding:0 9px; border:1px solid var(--app-border-soft); border-radius:8px; background:transparent; color:var(--app-link); font:inherit; font-size:12px; cursor:pointer; }
.source-trigger span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.source-trigger:hover { background:var(--app-hover); }
.source-trigger svg { width:16px; height:16px; flex-shrink:0; }
.source-panel { position:fixed; z-index:60; padding:18px; max-height:calc(100dvh - 130px); overflow:auto; background:var(--app-surface-raised); color:var(--app-text); border:1px solid var(--app-border); border-radius:12px; box-shadow:var(--app-shadow-panel); }
h2 { font-size:13px; font-weight:500; margin:0 0 12px; }
p { font-size:11px; color:var(--app-text-muted); line-height:1.8; margin:12px 0 0; }
@media(max-width:600px) { .source-trigger { max-width:220px; } .source-trigger span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; } }
</style>

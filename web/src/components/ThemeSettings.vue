<script setup lang="ts">
import { inject, onMounted, onUnmounted, ref, useId } from 'vue';
import { APPEARANCE, type Appearance, type ThemeMode } from '../appearance/theme';
import SettingsIcon from '~icons/lucide/settings-2';
defineProps<{ sidebar?: boolean; compact?: boolean }>();
const appearance = inject<Appearance>(APPEARANCE)!;
const mode = ref(appearance.mode);
const unsubscribe = appearance.subscribe(() => { mode.value = appearance.mode; });
const panel = ref<HTMLDetailsElement>();
const groupName = `appearance-${useId()}`;
const choices: { value: ThemeMode; label: string; hint: string }[] = [
  { value: 'light', label: '浅色', hint: '温暖的米色与柔绿' },
  { value: 'dark', label: '深色', hint: '低亮度的墨绿与暖灰' },
  { value: 'system', label: '跟随系统', hint: '随设备外观自动切换' },
];
function close(restore = false) {
  if (!panel.value?.open) return;
  panel.value.open = false;
  if (restore) panel.value.querySelector('summary')?.focus();
}
function outside(event: PointerEvent) { if (!panel.value?.contains(event.target as Node)) close(); }
onMounted(() => document.addEventListener('pointerdown', outside));
onUnmounted(() => { unsubscribe(); document.removeEventListener('pointerdown', outside); });
</script>
<template>
  <details ref="panel" class="theme-settings relative text-app-text" :class="{ 'sidebar-settings': sidebar }" @keydown.esc.stop.prevent="close(true)">
    <summary class="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-solid border-app-border bg-transparent px-3 py-2 text-xs text-app-muted hover:bg-app-surface focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-app-focus" aria-label="外观设置" title="外观设置">
      <SettingsIcon aria-hidden="true" width="18" height="18" /><span v-if="!compact">{{ sidebar ? '外观设置' : '外观' }}</span><span v-if="!sidebar" class="hidden sm:inline">· {{ choices.find(choice => choice.value === mode)?.label }}</span>
    </summary>
    <fieldset class="absolute right-0 z-50 m-0 mt-2 grid w-64 gap-1 rounded-xl border border-solid border-app-border bg-app-raised p-3 shadow-app-panel" aria-label="外观主题">
      <legend class="theme-legend">外观主题</legend>
      <label v-for="choice in choices" :key="choice.value" class="flex cursor-pointer items-center gap-3 rounded-lg p-3 hover:bg-app-surface" :class="{ 'bg-app-selected': mode === choice.value }">
        <input type="radio" :name="groupName" :value="choice.value" :checked="mode === choice.value" class="m-0 accent-app-accent" @change="appearance.select(choice.value)" />
        <span class="grid gap-1"><span class="text-sm">{{ choice.label }}</span><span class="text-xs text-app-muted">{{ choice.hint }}</span></span>
      </label>
    </fieldset>
  </details>
</template>
<style scoped>
.theme-settings { font-family: "Microsoft YaHei UI", sans-serif; }
.theme-settings summary { list-style: none; font: inherit; font-size: 12px; }
.theme-settings summary::-webkit-details-marker { display: none; }
.theme-settings input { width: 16px; height: 16px; }
.theme-legend { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.sidebar-settings summary { display:flex; width:100%; min-height:46px; padding:12px; gap:18px; border:0; white-space:nowrap; }
.sidebar-settings svg { flex-shrink:0; width:20px; height:20px; }
.sidebar-settings fieldset { position:fixed; top:auto; right:auto; bottom:76px; left:12px; width:min(280px,calc(100vw - 24px)); max-height:calc(100dvh - 100px); overflow:auto; z-index:60; }
</style>

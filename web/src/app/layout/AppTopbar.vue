<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BackIcon from '~icons/lucide/chevron-left'
import ForwardIcon from '~icons/lucide/chevron-right'
import GlobalSearch from '../../components/search/GlobalSearch.vue'
import SourceSelector from '../../components/search/SourceSelector.vue'
const router = useRouter(), route = useRoute(), revision = ref(0)
const stop = router.afterEach(() => { revision.value++ })
onUnmounted(stop)
const canBack = computed(() => { void revision.value; return typeof window.history.state?.back === 'string' })
const canForward = computed(() => { void revision.value; return typeof window.history.state?.forward === 'string' })
</script>
<template>
  <header class="app-topbar" :class="{ 'search-topbar': route.path === '/search' }">
    <div class="history-navigation">
      <button type="button" aria-label="后退" title="后退" :disabled="!canBack" @click="router.back()"><BackIcon aria-hidden="true" /></button>
      <button type="button" aria-label="前进" title="前进" :disabled="!canForward" @click="router.forward()"><ForwardIcon aria-hidden="true" /></button>
    </div>
    <GlobalSearch />
    <SourceSelector v-if="route.path === '/search'" />
  </header>
</template>
<style scoped>
.app-topbar { position:relative; z-index:25; display:grid; grid-template-columns:68px minmax(200px,480px) minmax(0,1fr); align-items:center; gap:16px; padding:22px 28px; min-width:0; border-bottom:1px solid var(--app-border-soft); background:var(--app-bg); }
.history-navigation { display:flex; gap:4px; flex-shrink:0; }
.history-navigation button { display:grid; place-items:center; width:32px; height:36px; border:0; border-radius:8px; background:transparent; color:var(--app-link); cursor:pointer; }
.history-navigation button:disabled { opacity:.3; cursor:default; }
.history-navigation button:hover:not(:disabled) { background:var(--app-hover); }
svg { width:20px; height:20px; }
@media(max-width:1100px) {
  .app-topbar { grid-template-columns:68px minmax(0,1fr); gap:8px 12px; padding:18px 20px; }
  .app-topbar :deep(.source-selector) { grid-column:2; }
}
@media(max-width:600px) {
  .app-topbar { grid-template-columns:minmax(0,1fr); padding:12px; gap:8px; }
  .history-navigation { display:none; }
  .app-topbar :deep(.global-search) { grid-column:1; width:100%; }
  .app-topbar :deep(.source-selector) { grid-column:1; grid-row:2; }
}
</style>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from './AppSidebar.vue'
import MobileTabBar from './MobileTabBar.vue'
import AppTopbar from './AppTopbar.vue'
import { readSidebarExpanded, SIDEBAR_KEY } from './sidebar-preference'
import {useCoreClient} from '../../composables/useCoreClient'
defineProps<{ immersive: boolean; searchQuery: string }>()
let saved: string | null = null
try { saved = localStorage.getItem(SIDEBAR_KEY) } catch { /* Session-only navigation. */ }
const expanded = ref(readSidebarExpanded(saved))
watch(expanded, value => {
  try { localStorage.setItem(SIDEBAR_KEY, JSON.stringify({ schemaVersion: 1, expanded: value })) } catch { /* Navigation remains usable. */ }
})
const route = useRoute(), content = ref<HTMLElement>()
const {player}=useCoreClient()
const home = computed(() => route.path === '/')
const hidePlayer = computed(() => home.value && !player.selected.value && !player.queue.entries.value.length)
const scrollPositions = new Map<string, number>()
watch(() => route.fullPath, (to, from) => {
  if (content.value) { scrollPositions.set(from, content.value.scrollTop); content.value.scrollTop = scrollPositions.get(to) ?? 0 }
}, { flush: 'post' })
</script>
<template>
  <div class="app-shell" :class="{ 'immersive-shell': immersive, 'sidebar-expanded': expanded, 'home-shell': home }">
    <AppSidebar v-show="!immersive" :expanded="expanded" :search-query="searchQuery" @toggle="expanded = !expanded" />
    <div class="app-workspace">
      <AppTopbar v-if="!home" v-show="!immersive" />
      <main id="app-content" ref="content" class="app-content" :class="{ 'full-screen-content': immersive, 'home-content': home, 'settings-content': route.path === '/settings' }" tabindex="-1">
        <slot />
      </main>
      <div v-show="!hidePlayer && !immersive" class="workspace-player"><slot name="player" /></div>
      <MobileTabBar v-if="!immersive" :search-query="searchQuery"/>
    </div>
    <!-- Constant location: audio, queue and global dialogs never belong to a route. -->
    <slot name="overlays" />
  </div>
</template>
<style scoped>
.app-shell { --sidebar-width:72px; display:grid; grid-template-columns:var(--sidebar-width) minmax(0,1fr); height:100dvh; overflow:hidden; transition:grid-template-columns .2s ease; }
.sidebar-expanded { --sidebar-width:228px; }
.app-workspace { grid-column:2; display:grid; grid-template-rows:auto minmax(0,1fr) auto; min-width:0; min-height:0; }
.app-workspace > :deep(.app-topbar) { grid-row:1; }
.app-content { grid-row:2; min-height:0; min-width:0; max-width:none; width:100%; margin:0; padding:32px clamp(24px,4vw,64px) 40px; overflow:auto; overscroll-behavior:contain; scrollbar-gutter:stable; }
.workspace-player { grid-row:3; min-width:0; container:player-workspace / inline-size; }
.workspace-player :deep(.player) { position:relative; inset:auto; width:100%; padding:14px 24px; }
.immersive-shell { grid-template-columns:minmax(0,1fr); transition:none; }
.immersive-shell .app-workspace { grid-column:1; }
.immersive-shell .workspace-player :deep(.player) { position:fixed; inset:auto 0 0; width:auto; }
.full-screen-content { padding:0; }
.home-content { padding:0; overflow:hidden; scrollbar-gutter:auto; }
.settings-content{scrollbar-width:none;scrollbar-gutter:auto;}
.settings-content::-webkit-scrollbar{display:none;}
@media(max-width:800px) { .app-content { padding:24px 20px 32px; } }
@media(max-width:760px) {
 .app-shell,.sidebar-expanded{grid-template-columns:minmax(0,1fr);transition:none;}
 .app-shell :deep(.app-sidebar){display:none;}
 .app-workspace{grid-column:1;grid-template-rows:auto minmax(0,1fr) auto auto;}
 .app-workspace > :deep(.mobile-tabbar){grid-row:4;}
 .app-content{padding:20px 16px 28px;}
 .workspace-player :deep(.player){padding:10px 12px;}
}
@media(prefers-reduced-motion:reduce) { .app-shell { transition:none; } }
/* Home owns the space released by its topbar/footer. The audio slot stays mounted. */
.home-shell .app-content { padding:0; }
</style>

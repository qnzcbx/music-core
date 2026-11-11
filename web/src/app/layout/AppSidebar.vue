<script setup lang="ts">
import { RouterLink } from 'vue-router'
import DiscIcon from '~icons/lucide/disc-3'
import OpenIcon from '~icons/lucide/panel-left-open'
import CloseIcon from '~icons/lucide/panel-left-close'
import { navigation } from './navigation'

defineProps<{ expanded: boolean; searchQuery: string }>()
defineEmits<{ toggle: [] }>()
</script>
<template>
  <aside class="app-sidebar" aria-label="应用导航" :data-expanded="expanded">
    <RouterLink to="/" class="shell-brand" aria-label="随心听 首页" title="随心听 首页">
      <DiscIcon aria-hidden="true" /><span class="sidebar-label wordmark">随心听</span>
    </RouterLink>
    <nav aria-label="主导航">
      <RouterLink v-for="item in navigation.filter(row => row.to !== '/settings')" :key="item.to"
        :to="item.to === '/search' && searchQuery ? { path: item.to, query: { q: searchQuery } } : item.to"
        :title="item.label" :aria-label="item.label" class="sidebar-link">
        <component :is="item.icon" aria-hidden="true" /><span class="sidebar-label">{{ item.label }}</span>
      </RouterLink>
    </nav>
    <div class="sidebar-foot">
      <span class="sidebar-label sidebar-caption">留一点时间，给音乐。</span>
      <RouterLink to="/settings" class="sidebar-link" aria-label="设置" title="设置"><component :is="navigation.find(row=>row.to==='/settings')!.icon" aria-hidden="true"/><span class="sidebar-label">设置</span></RouterLink>
      <button type="button" class="sidebar-toggle" :aria-label="expanded ? '收起侧栏' : '展开侧栏'"
        :title="expanded ? '收起侧栏' : '展开侧栏'" :aria-expanded="expanded" @click="$emit('toggle')">
        <component :is="expanded ? CloseIcon : OpenIcon" aria-hidden="true" />
        <span class="sidebar-label">收起侧栏</span>
      </button>
    </div>
  </aside>
</template>
<style scoped>
.app-sidebar { display:flex; flex-direction:column; min-width:0; min-height:0; max-height:none; padding:24px 12px 16px; border-left:0; border-right:1px solid var(--app-border-soft); background:var(--app-sidebar); overflow-x:hidden; overflow-y:auto; }
.app-sidebar svg { width:20px; height:20px; flex-shrink:0; }
.shell-brand, .sidebar-link, .sidebar-toggle { display:flex; align-items:center; gap:0; min-width:0; min-height:46px; padding:12px; border-radius:10px; white-space:nowrap; color:var(--app-text-muted); text-decoration:none; }
[data-expanded=true] :is(.shell-brand,.sidebar-link,.sidebar-toggle) { gap:18px; }
.shell-brand { color:var(--app-link); margin-bottom:48px; }
.shell-brand svg { width:22px; height:22px; }
.shell-brand .wordmark { font-size:22px; }
nav { display:grid; grid-template-columns:minmax(0,1fr); min-width:0; gap:10px; }
.sidebar-link { font-size:13px; }
.sidebar-link:hover, .sidebar-toggle:hover { background:var(--app-hover); color:var(--app-link); }
.sidebar-link.router-link-exact-active { background:var(--app-surface-raised); color:var(--app-link); box-shadow:0 2px 9px var(--app-shadow-soft); }
.sidebar-label { max-width:0; overflow:hidden; opacity:0; visibility:hidden; transition:opacity .18s; }
[data-expanded=true] .sidebar-label { max-width:170px; opacity:1; visibility:visible; }
.sidebar-foot { margin-top:auto; padding-top:32px; }
.sidebar-caption { display:block; font-size:11px; color:var(--app-text-soft); margin:0 14px 20px; white-space:nowrap; }
.sidebar-toggle { width:100%; border:0; background:transparent; font:inherit; font-size:12px; cursor:pointer; }
a:focus-visible, button:focus-visible { outline:2px solid var(--app-focus); outline-offset:-2px; }
@media(max-width:600px) { .app-sidebar { padding:16px 4px 10px; } .shell-brand { margin-bottom:30px; } }
@media(prefers-reduced-motion:reduce) { .sidebar-label { transition:none; } }
</style>

<script setup lang="ts">
import { navigation } from './navigation';
defineProps<{ searchQuery:string }>();
</script>
<template><nav class="mobile-tabbar" aria-label="移动导航"><RouterLink v-for="item in navigation" :key="item.to" :to="item.to === '/search' && searchQuery ? {path:item.to,query:{q:searchQuery}} : item.to"><component :is="item.icon" aria-hidden="true"/><span>{{ item.label }}</span></RouterLink></nav></template>
<style scoped>
.mobile-tabbar{display:none;background:var(--app-surface-raised);border-top:1px solid var(--app-border-soft);padding:5px 4px max(5px,env(safe-area-inset-bottom));}
a{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:48px;gap:3px;color:var(--app-text-muted);text-decoration:none;font-size:10px;border-radius:8px;}svg{width:21px;height:21px;}a.router-link-exact-active{color:var(--app-link);background:var(--app-selected);}
@media(max-width:760px){.mobile-tabbar{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));}}
</style>

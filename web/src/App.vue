<script setup lang="ts">
import './style.css';
import {RouterView} from 'vue-router';
import AppShell from './app/layout/AppShell.vue';
import SearchRouteSync from './app/router/SearchRouteSync.vue';
import BottomPlayer from './components/BottomPlayer.vue';
import {provideCoreClient} from './composables/useCoreClient';
import {providePlayerVisuals} from './composables/usePlayerTransition';
import {onMounted,ref} from 'vue';
const {searchState:{query},player}=provideCoreClient();
const {immersive}=providePlayerVisuals(player.selected,player.queue.current);
const audioHost=ref<HTMLElement>();
onMounted(()=>audioHost.value?.append(player.audio));
</script>
<template><div ref="audioHost" hidden data-audio-host/><SearchRouteSync/><AppShell :immersive="immersive" :search-query="query"><RouterView/><template #player><BottomPlayer/></template></AppShell></template>

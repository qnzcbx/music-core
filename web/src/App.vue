<script setup lang="ts">
import './style.css';
import {RouterView} from 'vue-router';
import AppShell from './app/layout/AppShell.vue';
import SearchRouteSync from './app/router/SearchRouteSync.vue';
import BottomPlayer from './components/BottomPlayer.vue';
import {provideCoreClient} from './composables/useCoreClient';
import {providePlayerVisuals} from './composables/usePlayerTransition';
import {usePlayerStore} from './stores/player';
const {searchState:{query}}=provideCoreClient();
const {currentSong,currentQueueKey}=usePlayerStore();
providePlayerVisuals(currentSong,currentQueueKey);
</script>
<template><SearchRouteSync/><AppShell :immersive="false" :search-query="query"><RouterView/><template #player><BottomPlayer/></template></AppShell></template>

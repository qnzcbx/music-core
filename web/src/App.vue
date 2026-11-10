<script setup lang="ts">
import './style.css';
import {RouterView} from 'vue-router';
import AppShell from './app/layout/AppShell.vue';
import SearchRouteSync from './app/router/SearchRouteSync.vue';
import BottomPlayer from './components/BottomPlayer.vue';
import {provideCoreClient} from './composables/useCoreClient';
import {providePlayerVisuals} from './composables/usePlayerTransition';
import {ref} from 'vue';
const {searchState:{query}}=provideCoreClient();
providePlayerVisuals(ref(null),ref(null));
</script>
<template><SearchRouteSync/><AppShell :immersive="false" :search-query="query"><RouterView/><template #player><BottomPlayer/></template></AppShell></template>

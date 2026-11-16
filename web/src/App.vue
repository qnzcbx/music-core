<script setup lang="ts">
import './style.css';
import {isDesktop} from './api/transport';
import {RouterView} from 'vue-router';
import AppShell from './app/layout/AppShell.vue';
import SearchRouteSync from './app/router/SearchRouteSync.vue';
import DownloadQualityDialog from './components/DownloadQualityDialog.vue';
import ClientNotice from './components/ClientNotice.vue';
import BottomPlayer from './components/BottomPlayer.vue';
import {provideCoreClient} from './composables/useCoreClient';
import {providePlayerVisuals} from './composables/usePlayerTransition';
import {onMounted,ref} from 'vue';
const {searchState:{query},player}=provideCoreClient();
const {immersive}=providePlayerVisuals(player.selected,player.queue.current);
const audioHost=ref<HTMLElement>();
onMounted(()=>audioHost.value?.append(player.audio));
</script>
<template><div ref="audioHost" hidden data-audio-host/><SearchRouteSync/><ClientNotice/><DownloadQualityDialog/><AppShell :immersive="immersive" :search-query="query"><p v-if="isDesktop" role="status" style="padding:8px 20px">桌面预览：仅迁移酷我搜索和播放。其他来源、歌词、下载、本机音乐库及目录管理尚未迁移。</p><RouterView/><template #player><BottomPlayer/></template></AppShell></template>

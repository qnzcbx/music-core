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
<template><div ref="audioHost" hidden data-audio-host/><SearchRouteSync/><ClientNotice/><DownloadQualityDialog/><AppShell :immersive="immersive" :search-query="query"><p v-if="isDesktop" role="status" style="padding:8px 20px">桌面预览：已接入四个来源的官方匿名搜索与播放接口，部分曲目受来源权限或网络限制。仅支持已确认可保存的酷我标准品质原格式下载；其他来源下载、转码、本机音乐库及目录管理暂不支持。</p><RouterView/><template #player><BottomPlayer/></template></AppShell></template>

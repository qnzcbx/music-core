<script setup lang="ts">
import {computed,ref} from 'vue';
import SongList from '../components/SongList.vue';
import {useCoreClient} from '../composables/useCoreClient';
import {useSongGroups} from '../composables/useSongGroups';
import type {Song} from '../types/music';
const {searchState,player}=useCoreClient();const {query,songs,busy,error,perSourceStatus,loadingMore,cursors}=searchState;
const groupsState=useSongGroups(songs,searchState.providers,ref<Song|null>(null));const {groups,now}=groupsState;
const hasMore=computed(()=>Object.values(cursors.value).some(Boolean));
</script>
<template><section class="search-view"><header class="search-results-header"><div><h1 class="page-title">{{query?'“'+query+'”':'搜索音乐'}}</h1><p class="results-count">歌曲 · 共 {{groups.length}} 组结果 · {{songs.length}} 个版本</p></div></header>
<p role="status">{{busy?'正在搜索…':songs.length?'搜索完成':'搜索后，歌曲会出现在这里。'}}</p><p v-if="error" role="alert">{{error}}</p><p v-for="(state,source) in perSourceStatus" :key="source" v-show="state.status==='failed'">{{source}}：{{state.message}}</p><p class="notice">点击具体版本播放，或通过歌曲操作添加到播放队列。</p>
<SongList :songs="songs" :groups="groups" :now="now" :busy="busy" :pre-resolve-enabled="false" :submitting="true" :download-jobs="{}" :active-id="player.selectedId.value" @play="player.select" @toggle="groupsState.toggle"/>
<button v-if="hasMore" :disabled="busy||loadingMore" @click="searchState.loadMore()">{{loadingMore?'加载中…':'加载更多'}}</button></section></template>
<style scoped>
.search-view {
  width: 100%;
  min-width: 0;
  max-width: 1500px;
  margin-inline: auto;
}
.search-results-header {
  position: relative;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 18px;
  padding: 0 0 20px;
  border: 0;
}
h1 {
  font:
    500 29px/1.5 "Songti SC",
    "SimSun",
    serif;
  margin: 0 0 8px;
  overflow-wrap: anywhere;
}
.results-count {
  margin: 0;
  color: var(--app-text-muted);
  font-size: 12px;
}
.results-count small {
  font-size: 11px;
}
.search-result-tools {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
}
.update-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: transparent;
  color: var(--app-link);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.update-search svg {
  width: 15px;
  height: 15px;
}
.update-search:hover {
  background: var(--app-hover);
}
.compact-search-status {
  margin: 0 0 12px;
  min-height: 20px;
  font-size: 11px;
}
.source-change-hint {
  color: var(--app-text-muted);
  font-size: 12px;
  margin: 0 0 10px;
}
.search-options-menu {
  position: relative;
  font-size: 11px;
  color: var(--app-text-muted);
}
.search-options-menu summary {
  cursor: pointer;
  padding: 9px 0;
}
.search-options-menu > div {
  position: absolute;
  right: 0;
  top: 36px;
  z-index: 10;
  width: 280px;
  max-width: calc(100vw - 90px);
  padding: 16px;
  background: var(--app-surface-raised);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  box-shadow: var(--app-shadow-panel);
  line-height: 1.8;
}
.search-options-menu label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.search-options-menu input {
  width: 16px;
  height: 16px;
  accent-color: var(--app-accent);
}
.search-options-menu p {
  font-size: 11px;
  margin: 10px 0 0;
}
@media (max-width: 600px) {
  .search-results-header {
    gap: 10px;
  }
  .search-result-tools {
    width: 100%;
    margin-left: 0;
    justify-content: space-between;
  }
  h1 {
    font-size: 25px;
  }
}
</style>

<script setup lang="ts">
import { computed, nextTick,ref,watch } from "vue";
import {useEventListener,useInfiniteScroll} from '@vueuse/core';
import SongList from "../components/SongList.vue";
import { useCoreClient } from "../composables/useCoreClient";
import { useSongGroups } from "../composables/useSongGroups";
import type { Song } from "../types/music";
const { searchState, player } = useCoreClient();
const { query, songs, busy, error, perSourceStatus, loadingMore, cursors } = searchState;
const groupsState = useSongGroups(songs, searchState.providers, ref<Song | null>(null));
const { groups, now } = groupsState;
const hasMore = computed(() => Object.values(cursors.value).some(Boolean));
const pending = computed(() => Object.values(perSourceStatus.value).some(state=>state.status==='running'));
const host=ref<HTMLElement>();
const container=computed(()=>host.value?.closest<HTMLElement>('#app-content'));
const autoFill=ref(2),gesture=ref(false);
const infinite=useInfiniteScroll(container,async()=>{
 if(gesture.value)gesture.value=false;else autoFill.value--;
 groupsState.lockRepresentatives();await searchState.loadMore();
},{distance:320,interval:180,canLoadMore:()=>searchState.canLoadMore.value&&(autoFill.value>0||gesture.value)});
function permit(){gesture.value=true;infinite.reset();}
useEventListener(container,'wheel',event=>{if(event.deltaY>0)permit();},{passive:true});
let touchY=0;
useEventListener(container,'touchstart',event=>{touchY=event.touches[0]?.clientY??0;},{passive:true});
useEventListener(container,'touchmove',event=>{if((event.touches[0]?.clientY??touchY)<touchY)permit();},{passive:true});
useEventListener(container,'keydown',event=>{if(['ArrowDown','PageDown','End',' '].includes(event.key))permit();});
watch(searchState.searchRevision,()=>{autoFill.value=2;gesture.value=false;void nextTick(()=>{if(container.value)container.value.scrollTop=0;infinite.reset();});});
// 在响应落入DOM前记录可见歌曲；展开组内插入版本也保留阅读位置。
watch(()=>songs.value.length,(length,previous)=>{
 if(length<=previous||!container.value)return;
 const box=container.value,top=box.getBoundingClientRect().top;
 const anchor=Array.from(host.value?.querySelectorAll<HTMLElement>('.song-row')??[]).find(row=>row.getBoundingClientRect().bottom>top+8);
 if(!anchor)return;const before=anchor.getBoundingClientRect().top;
 void nextTick(()=>{if(anchor.isConnected&&container.value===box)box.scrollTop+=anchor.getBoundingClientRect().top-before;});
},{flush:'pre'});
function retrySource(source:string){groupsState.lockRepresentatives();void searchState.retry(source);}
</script>
<template>
  <section ref="host" class="search-view">
    <header class="search-results-header">
      <div>
        <h1 class="page-title">{{ query ? "“" + query + "”" : "搜索音乐" }}</h1>
        <p class="results-count">
          {{pending||hasMore||error?'已加载':'共'}} {{songs.length}} 首 · {{groups.length}} 组结果
        </p>
      </div>
    </header>
    <p role="status">
      {{ busy ? "正在搜索…" : songs.length ? "搜索完成" : "搜索后，歌曲会出现在这里。" }}
    </p>
    <SongList
      :songs="songs"
      :groups="groups"
      :now="now"
      :busy="busy"
      :pre-resolve-enabled="false"
      :submitting="true"
      :download-jobs="{}"
      :active-id="player.selectedId.value"
      @play="player.select"
      @toggle="groupsState.toggle"
    />
    <div class="search-pagination" aria-live="polite">
      <p v-if="pending">正在加载…</p>
      <p v-for="(state,source) in perSourceStatus" :key="source" v-show="state.status==='failed'" role="alert">{{source}}：{{state.message}} <button @click="retrySource(source)">重试此来源</button></p>
      <p v-if="!pending&&!hasMore&&!error&&searchState.resultSources.value.length">已全部加载</p>
      <p v-else-if="hasMore&&!loadingMore&&!busy">继续向下滚动</p>
    </div>
  </section>
</template>
<style scoped>
.search-view {
  width: 100%;
  min-width: 0;
  max-width: 1500px;
  margin-inline: auto;
}
.search-pagination{min-height:48px;text-align:center;padding:18px 0;color:var(--app-text-muted);font-size:12px}.search-pagination button{border:0;background:transparent;color:var(--app-link);cursor:pointer;padding:6px 10px;font:inherit}
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

import { ref } from 'vue';
import { useStorage } from '@vueuse/core';
import { useProviders } from './useProviders';
import { searchSource } from '../api/search';
import type { ProviderId } from '../types/core';
import type { SearchEntry } from '../types/music';

export function useCoreSearch(){
 const {providers,providerError,load}=useProviders();
 const sources=useStorage<string[]>('music-core.search.sources.v1',['kuwo']);
 sources.value=Array.isArray(sources.value)?sources.value.filter(p=>['kuwo','qq','netease','migu'].includes(p)):['kuwo'];
 if(!sources.value.length)sources.value=['kuwo'];
 const query=ref(''),resultSources=ref<string[]>([]),songs=ref<SearchEntry[]>([]),busy=ref(false),loadingMore=ref(false),error=ref(''),searchRevision=ref('');
 const cursors=ref<Record<string,string|null>>({});const perSourceStatus=ref<Record<string,{status:string;message?:string}>>({});
 let generation=0,controller:AbortController|undefined;
 async function run(more=false){
  if(!query.value.trim()||!sources.value.length)return;
  controller?.abort();controller=new AbortController();const signal=controller.signal,version=++generation;
  const selected=more?resultSources.value.filter(p=>cursors.value[p]):[...sources.value];
  if(!more){songs.value=[];cursors.value={};perSourceStatus.value={};resultSources.value=selected;searchRevision.value=String(version);}
  busy.value=!more;loadingMore.value=more;error.value='';
  await Promise.all(selected.map(async source=>{
   perSourceStatus.value[source]={status:'running'};
   try{
    const page=await searchSource(source as ProviderId,query.value,more?cursors.value[source]??null:null,signal);
    if(version!==generation)return;
    const known=new Set(songs.value.map(s=>s.id));
    songs.value.push(...page.items.filter(row=>!known.has(JSON.stringify([row.identity.providerId,row.identity.platformId]))).map(row=>({
     id:JSON.stringify([row.identity.providerId,row.identity.platformId]),identity:row.identity,source:row.identity.providerId,platformId:row.identity.platformId,mid:row.identity.platformId,
     title:row.title,name:row.title,artist:(row.artists??[]).join('、'),album:row.album??'',duration:row.durationSeconds??null,cover:row.cover??null,resolveState:'idle' as const,
    })));
    cursors.value[source]=page.nextCursor??null;perSourceStatus.value[source]={status:'completed'};
   }catch(reason){if(version!==generation)return;perSourceStatus.value[source]={status:'failed',message:reason instanceof Error?reason.message:'搜索失败'};error.value='部分来源搜索失败，其他结果已保留。';}
  }));
  if(version===generation){busy.value=false;loadingMore.value=false;}
 }
 void load().catch(()=>{});
 return {query,sources,resultSources,songs,busy,loadingMore,error,searchRevision,providers,providerError,loadProviders:load,cursors,perSourceStatus,search:()=>run(),loadMore:()=>run(true)};
}

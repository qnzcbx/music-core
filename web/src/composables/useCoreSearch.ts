import { computed,onScopeDispose,ref,watch } from 'vue';
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
 const query=ref(''),resultSources=ref<string[]>([]),songs=ref<SearchEntry[]>([]),busy=ref(false),searchRevision=ref('');
 const cursors=ref<Record<string,string|null>>({});
 const perSourceStatus=ref<Record<string,{status:'running'|'completed'|'failed';message?:string;requestedCursor:string|null}>>({});
 const running=new Map<string,AbortController>(),completed=new Set<string>();
 let generation=0,activeQuery='';
 const requestKey=(source:string,cursor:string|null)=>JSON.stringify([source,cursor]);
 function reset(){
  generation++;for(const request of running.values())request.abort();running.clear();completed.clear();
  songs.value=[];cursors.value={};perSourceStatus.value={};resultSources.value=[];busy.value=false;searchRevision.value=String(generation);
 }
 function clear(){
  query.value='';
  activeQuery='';
  reset();
 }
 async function requestPage(source:string,cursor:string|null,version:number){
  const key=requestKey(source,cursor);
  if(version!==generation||running.has(source)||completed.has(key))return;
  const request=new AbortController();running.set(source,request);
  perSourceStatus.value[source]={status:'running',requestedCursor:cursor};
  try{
   const page=await searchSource(source as ProviderId,activeQuery,cursor,request.signal);
   if(version!==generation)return;
   const known=new Set(songs.value.map(song=>song.id));
   for(const row of page.items){
    const id=JSON.stringify([row.identity.providerId,row.identity.platformId]);
    if(known.has(id))continue;known.add(id);
    songs.value.push({id,identity:row.identity,source:row.identity.providerId,platformId:row.identity.platformId,mid:row.identity.platformId,
     trackAccess:row.downloadAllowed===undefined?undefined:{playback:{state:'unknown',reason:'',evidence:'metadata'},download:{state:row.downloadAllowed?'allowed':'denied',reason:row.downloadAllowed?'':'桌面下载暂未支持此来源或未确认该曲目可保存',evidence:'desktop-source-policy'}},title:row.title,name:row.title,artist:(row.artists??[]).join('、'),album:row.album??'',duration:row.durationSeconds??null,cover:row.cover??null,resolveState:'idle'});
   }
   completed.add(key);
   const next=page.nextCursor??null;
   cursors.value[source]=next&&!completed.has(requestKey(source,next))?next:null;
   perSourceStatus.value[source]={status:'completed',requestedCursor:cursor};
  }catch(reason){
   if(version===generation&&!request.signal.aborted)perSourceStatus.value[source]={status:'failed',requestedCursor:cursor,message:reason instanceof Error?reason.message:'搜索失败'};
  }finally{if(running.get(source)===request)running.delete(source);}
 }
 async function search(){
  reset();if(!query.value.trim()||!sources.value.length)return;
  activeQuery=query.value.trim();resultSources.value=[...sources.value];const version=generation;busy.value=true;
  await Promise.all(resultSources.value.map(source=>requestPage(source,null,version)));
  if(version===generation)busy.value=false;
 }
 const eligibleSources=computed(()=>resultSources.value.filter(source=>cursors.value[source]&&perSourceStatus.value[source]?.status==='completed'));
 async function loadMore(){const requests=eligibleSources.value.map(source=>requestPage(source,cursors.value[source]!,generation));if(requests.length)await Promise.race(requests);}
 async function retry(source:string){const state=perSourceStatus.value[source];if(state?.status==='failed')await requestPage(source,state.requestedCursor,generation);}
 const loadingMore=computed(()=>Object.values(perSourceStatus.value).some(state=>state.status==='running'&&state.requestedCursor!==null));
 const error=computed(()=>Object.values(perSourceStatus.value).some(state=>state.status==='failed')?'部分来源搜索失败，已有结果已保留。':'');
 watch(()=>sources.value.join('|'),reset,{flush:'sync'});
 onScopeDispose(()=>{generation++;for(const request of running.values())request.abort();});
 void load().catch(()=>{});
 return {query,sources,resultSources,songs,busy,loadingMore,error,searchRevision,providers,providerError,loadProviders:load,cursors,perSourceStatus,search,clear,loadMore,retry,canLoadMore:computed(()=>eligibleSources.value.length>0)};
}

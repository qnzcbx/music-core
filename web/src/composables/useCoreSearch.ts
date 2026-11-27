import { computed,onScopeDispose,ref,watch } from 'vue';
import { useStorage } from '@vueuse/core';
import { useProviders } from './useProviders';
import { searchSource } from '../api/search';
import type { ProviderId } from '../types/core';
import type { SearchEntry } from '../types/music';
import { isTrackIdentity, queueKey } from '../utils/player-queue';

export function useCoreSearch(){
 const {providers,providerError,load}=useProviders();
 const savedSources = useStorage<string[] | null>('music-core.search.sources.v1', null, undefined, {
  serializer: { read: JSON.parse, write: JSON.stringify },
 });
 const sources = computed<string[]>({
  get() {
   const available = providers.value.filter((provider) => provider.capabilities?.search);
   const saved = savedSources.value;
   const selected = Array.isArray(saved) ? available.filter((provider) => saved.includes(provider.id)) : [];
   if (selected.length) return selected.map((provider) => provider.id);
   const defaults = available.filter((provider) => provider.defaultSelected);
   return (defaults.length ? defaults : available.slice(0, 1)).map((provider) => provider.id);
  },
  set(value) { savedSources.value = value; },
 });
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
    if (!isTrackIdentity(row.identity)) continue;
    const id = queueKey(row.identity);
    if (known.has(id)) continue;
    known.add(id);
    songs.value.push({
      id, identity: row.identity, title: row.title, artist: (row.artists ?? []).join('、'),
      album: row.album ?? '', duration: row.durationSeconds ?? null, cover: row.cover ?? null,
      downloadAllowed: row.downloadAllowed,
    });
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
  const requested = query.value.trim();
  reset();
  if (!requested) return;
  if (!providers.value.length) {
   try { await load(); } catch { return; }
  }
  if (requested !== query.value.trim() || !sources.value.length) return;
  activeQuery = requested;
  resultSources.value = [...sources.value];
  const version = generation;
  busy.value = true;
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

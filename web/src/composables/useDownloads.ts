import {computed,onMounted,onScopeDispose,ref,shallowRef} from 'vue';
import {createDownload,listDownloads,listDownloadFiles,updateDownload,removeDownloadFile} from '../api/downloads';
import {ApiError} from '../api/http';
import {trackIdentity,queueKey} from '../utils/player-queue';
import type {SearchEntry} from '../types/music';
import type {DownloadTask,SavedDownloadFile} from '../types/core';

export const activeDownload=(task:DownloadTask)=>['queued','resolving','downloading'].includes(task.status);
export function useDownloads(){
 const tasks=shallowRef<DownloadTask[]>([]),files=shallowRef<SavedDownloadFile[]>([]),loading=ref(false),error=ref(''),fileError=ref('');
 const feedback=ref<{key:string;text:string;error?:boolean;taskId?:string}|null>(null),pending=ref(new Set<string>()),covers=ref<Record<string,string|null>>({}),retried=ref<Record<string,string>>({});
 let revision=0,disposed=false,timer:ReturnType<typeof setTimeout>|undefined,inflight:Promise<void>|undefined,again=false,wantFiles=false;
 const queries=new Set<AbortController>(),operations=new Map<string,Promise<DownloadTask|undefined>>();
 const active=computed(()=>tasks.value.some(activeDownload));
 const message=(reason:unknown)=>reason instanceof TypeError?'无法连接下载服务，请稍后重试':reason instanceof Error?(reason.name==='AbortError'?'请求超时，请稍后重试':reason.message):'下载操作失败';
 function arm(){clearTimeout(timer);if(!disposed&&!document.hidden&&active.value)timer=setTimeout(()=>void refresh(false),error.value?5000:1500);}
 function upsert(task:DownloadTask){const old=tasks.value.find(t=>t.id===task.id);if(old&&old.updatedAt>task.updatedAt)return;tasks.value=[...tasks.value.filter(t=>t.id!==task.id),task];}
 function refresh(withFiles=true):Promise<void>{
  if(disposed)return Promise.resolve();
  if(withFiles)wantFiles=true;
  if(inflight)return inflight;
  clearTimeout(timer);loading.value=true;const token=revision,request=new AbortController();queries.add(request);
  inflight=(async()=>{
   try{const data=await listDownloads(request.signal);if(disposed||token!==revision)return;
    const completed=data.some(t=>t.status==='completed'&&tasks.value.find(old=>old.id===t.id)?.status!=='completed');
    tasks.value=data;error.value='';
    if(wantFiles||completed){wantFiles=false;try{const saved=await listDownloadFiles(request.signal);if(!disposed&&token===revision){files.value=saved;fileError.value='';}}catch(reason){if(!disposed&&token===revision)fileError.value=message(reason);}}
   }catch(reason){if(!disposed&&token===revision)error.value=message(reason);}
   finally{queries.delete(request);inflight=undefined;loading.value=false;if((again||wantFiles&&!error.value)&&!disposed){again=false;void refresh();}else arm();}
  })();return inflight;
 }
 async function perform(key:string,action:()=>Promise<DownloadTask>,notice:string){
  const running=operations.get(key);if(running)return running;
  revision++;pending.value=new Set([...pending.value,key]);feedback.value=null;
  const work=(async()=>{try{const task=await action();if(disposed)return;upsert(task);feedback.value={key,taskId:task.id,text:task.status==='failed'?'下载失败':notice,error:task.status==='failed'};if(task.status==='failed')console.error('下载失败',{identity:task.identity,code:task.errorCode});return task;}
   catch(reason){console.error("下载请求失败",reason);if(!disposed)feedback.value={key,error:true,text:reason instanceof ApiError&&reason.status===404?'任务不存在或已过期，请刷新':reason instanceof ApiError&&reason.status===429?'下载任务过多，请稍后重试':message(reason)};}
   finally{operations.delete(key);const next=new Set(pending.value);next.delete(key);pending.value=next;revision++;if(inflight)again=true;else void refresh();}
  })();operations.set(key,work);return work;
 }
 async function create(song:SearchEntry){
  const identity=trackIdentity(song),key=queueKey(identity);
  const existing=[...tasks.value].reverse().find(task=>queueKey(task.identity)===key);
  if(existing){feedback.value={key,text:existing.status==='completed'?'该版本已有完成记录，可在下载页查看':activeDownload(existing)?'该歌曲已在下载任务中':'该版本已有任务，可在下载页重试'};return existing;}
  covers.value[key]=song.cover??null;
  return perform(key,()=>createDownload({identity,title:song.title||song.name,artist:song.artist}),'已加入下载任务');
 }
 async function operate(task:DownloadTask,operation:'cancel'|'retry'){
  if(operation==='retry'&&retried.value[task.id])return;
  const result=await perform(task.id,()=>updateDownload(task.id,operation),operation==='retry'?'已重新开始下载':'已更新任务状态');
  if(result&&operation==='retry')retried.value={...retried.value,[task.id]:result.id};
  return result;
 }
 async function removeFile(file:SavedDownloadFile,deleteFile:boolean){
  if(pending.value.has(file.fileId))return false;
  revision++;pending.value=new Set([...pending.value,file.fileId]);feedback.value=null;
  try{await removeDownloadFile(file.fileId,deleteFile);files.value=files.value.filter(f=>f.fileId!==file.fileId);feedback.value={key:file.fileId,text:deleteFile?'已删除本地音频文件':'已移除下载记录，文件仍保留'};return true;}
  catch(reason){fileError.value=message(reason);return false;}
  finally{const next=new Set(pending.value);next.delete(file.fileId);pending.value=next;revision++;if(inflight)again=true;else void refresh();}
 }
 const visible=()=>{if(document.hidden)clearTimeout(timer);else void refresh();};
 onMounted(()=>{void refresh();document.addEventListener('visibilitychange',visible);});
 onScopeDispose(()=>{disposed=true;clearTimeout(timer);for(const request of queries)request.abort();document.removeEventListener('visibilitychange',visible);});
 return {tasks,files,loading,error,fileError,feedback,pending,covers,retried,active,create,operate,refresh,removeFile};
}

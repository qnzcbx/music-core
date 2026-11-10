import {computed,onUnmounted,ref,shallowRef} from 'vue';
import {useStorage} from '@vueuse/core';
import {RecoveryPlayer} from './recovery-player.mjs';
import {playbackRequest} from '../api/playback';
import {isLocalSong,type PlayableSong} from '../types/music';
import {localStreamUrl} from '../api/downloads';
import type {SavedDownloadFile,DownloadTask} from '../types/core';
import {trackIdentity} from '../utils/player-queue';
import {useQueue} from './useQueue';

/** 根提供者创建一次，路由页面不拥有音频或续期任务。 */
export function usePlayer(){
 const audio=document.createElement('audio');audio.preload='metadata';audio.hidden=true;
 const selected=shallowRef<PlayableSong|null>(null),time=ref(0),duration=ref(0),playing=ref(false),message=ref('选择歌曲开始播放'),phase=ref('idle'),muted=ref(false);
 const volume=useStorage('music-core.volume.v1',1);audio.volume=Math.max(0,Math.min(1,Number(volume.value)||0));
 let timer:ReturnType<typeof setTimeout>|undefined, disposed=false, selectionRevision=0;
 const localIntent=ref(false);
 const local=computed(()=>!!selected.value&&isLocalSong(selected.value));
 let scheduledSession:typeof controller.session=null;
 function schedule(){const session=controller.session;if(!session||disposed||local.value)return;
  if(timer!==undefined&&scheduledSession===session)return;
  clearTimeout(timer);scheduledSession=session;
  timer=setTimeout(async()=>{timer=undefined;await controller.renew();if(controller.session===session)schedule();},Math.max(100,session.expiresInSeconds*500));
 }
 const controller=new RecoveryPlayer(audio,{request:playbackRequest,notify:state=>{
  if(local.value)return;
  phase.value=state.phase;message.value=state.message;
  if(state.phase==='opening'){clearTimeout(timer);timer=undefined;}
  if(state.phase==='ready'||state.phase==='blocked')schedule();
  if(state.phase==='idle')clearTimeout(timer);
 }});
 const listeners:([string,EventListener])[]=[];
 function listen(event:string,handler:()=>void){audio.addEventListener(event,handler);listeners.push([event,handler]);}
 function sync(){time.value=Number.isFinite(audio.currentTime)?audio.currentTime:0;duration.value=Number.isFinite(audio.duration)?audio.duration:0;playing.value=!audio.paused&&!audio.ended;}
 for(const event of ['loadedmetadata','durationchange','timeupdate','seeking','seeked','playing','pause','ended','emptied'])listen(event,sync);
 listen('volumechange',()=>{volume.value=audio.volume;muted.value=audio.muted;});
 listen('waiting',()=>{message.value='正在缓冲';});
 listen('playing',()=>{message.value='正在播放';if(local.value)phase.value='ready';});
 listen('error',()=>{if(local.value){phase.value='error';localIntent.value=false;message.value='本地文件无法读取、已变化或格式不支持，请刷新下载列表';}});
 listen('ended',()=>{if(!selected.value||!audio.ended)return;message.value='播放结束';
  if(queue.navigation.mode==='repeat_one'&&selected.value){seek(0);void setPlaying(true);}
  else void queue.advance(true);
 });
 const selectedId=computed(()=>selected.value?.id);
 const intentRevision=ref(0);
 const playIntent=computed(()=>{void intentRevision.value;void phase.value;return local.value?localIntent.value:controller.desiredPlaying;});
 async function select(song:PlayableSong){
  const revision=++selectionRevision;clearTimeout(timer);timer=undefined;selected.value=song;
  if(!isLocalSong(song)){localIntent.value=false;await controller.select(trackIdentity(song));return;}
  phase.value='opening';message.value='正在打开本地文件';localIntent.value=true;
  await controller.stop();
  if(revision!==selectionRevision||disposed)return;
  audio.src=localStreamUrl(song.fileId);audio.load();
  if(!localIntent.value){phase.value='ready';message.value='已暂停';return;}
  try{await audio.play();if(revision===selectionRevision){phase.value='ready';message.value='正在播放';}}
  catch(reason){if(revision!==selectionRevision)return;if(reason instanceof DOMException&&reason.name==='AbortError'&&!localIntent.value){phase.value='ready';message.value='已暂停';}else if(reason instanceof DOMException&&reason.name==='NotAllowedError'){phase.value='blocked';message.value='点击播放本地文件';}else{phase.value='error';localIntent.value=false;message.value='本地文件无法读取、已变化或格式不支持，请刷新下载列表';}}
 }
 async function stop(){selectionRevision++;clearTimeout(timer);timer=undefined;selected.value=null;localIntent.value=false;await controller.stop();}
 function seek(value:number){if(local.value){if(Number.isFinite(audio.duration))audio.currentTime=Math.max(0,Math.min(value,audio.duration));}else controller.seek(value);}
 async function setPlaying(value:boolean){
  if(!local.value)return controller.setPlaying(value);
  const revision=selectionRevision;localIntent.value=value;if(!value){audio.pause();return;}
  try{await audio.play();}catch{if(revision!==selectionRevision)return;message.value='本地文件无法播放，请刷新列表后重试';phase.value='error';localIntent.value=false;}
 }
 let storage:Storage|undefined;try{storage=window.localStorage;}catch{/* 无存储也能播放。 */}
 const queue=useQueue(select,stop,()=>local.value?['ready','blocked'].includes(phase.value):!!controller.session&&['ready','blocked'].includes(controller.phase),Math.random,storage);
 function setVolume(value:number){audio.volume=Math.max(0,Math.min(1,value));audio.muted=false;volume.value=audio.volume;muted.value=audio.muted;}
 const pagehide=()=>{void stop();};window.addEventListener('pagehide',pagehide);
 onUnmounted(()=>{disposed=true;clearTimeout(timer);window.removeEventListener('pagehide',pagehide);for(const [event,handler] of listeners)audio.removeEventListener(event,handler);void controller.dispose();audio.remove();});
 return {audio,selected,selectedId,time,duration,playing,playIntent,muted,volume,message,phase,queue,select:queue.select,stop,setVolume,
  selectLocal:(file:SavedDownloadFile,task?:DownloadTask)=>queue.select({kind:'local',fileId:file.fileId,id:JSON.stringify(['local',file.fileId]),source:'local',name:task?.title||file.filename,title:task?.title||file.filename,artist:task?.artist||'',album:'',cover:null,duration:null}),
  removeLocal:(fileId:string)=>queue.remove(JSON.stringify(['local',fileId])),
  toggle:()=>{const ended=audio.ended;if(ended)seek(0);const result=setPlaying(ended||!playIntent.value);intentRevision.value++;return result;},mute:()=>{audio.muted=!audio.muted;},seek,retry:()=>local.value&&selected.value?select(selected.value):controller.recover(false)};
}

import {computed,onUnmounted,ref,shallowRef} from 'vue';
import {useStorage} from '@vueuse/core';
import {RecoveryPlayer} from './recovery-player.mjs';
import {playbackRequest} from '../api/playback';
import type {SearchEntry} from '../types/music';
import {trackIdentity} from '../utils/player-queue';
import {useQueue} from './useQueue';

/** 根提供者创建一次，路由页面不拥有音频或续期任务。 */
export function usePlayer(){
 const audio=document.createElement('audio');audio.preload='metadata';audio.hidden=true;
 const selected=shallowRef<SearchEntry|null>(null),time=ref(0),duration=ref(0),playing=ref(false),message=ref('选择歌曲开始播放'),phase=ref('idle'),muted=ref(false);
 const volume=useStorage('music-core.volume.v1',1);audio.volume=Math.max(0,Math.min(1,Number(volume.value)||0));
 let timer:ReturnType<typeof setTimeout>|undefined, disposed=false;
 let scheduledSession:typeof controller.session=null;
 function schedule(){const session=controller.session;if(!session||disposed)return;
  if(timer!==undefined&&scheduledSession===session)return;
  clearTimeout(timer);scheduledSession=session;
  timer=setTimeout(async()=>{timer=undefined;await controller.renew();if(controller.session===session)schedule();},Math.max(100,session.expiresInSeconds*500));
 }
 const controller=new RecoveryPlayer(audio,{request:playbackRequest,notify:state=>{
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
 listen('playing',()=>{message.value='正在播放';});
 listen('ended',()=>{if(!selected.value||!audio.ended)return;message.value='播放结束';
  if(queue.navigation.mode==='repeat_one'&&selected.value){controller.seek(0);void controller.setPlaying(true);}
  else void queue.advance(true);
 });
 const selectedId=computed(()=>selected.value?.id);
 const intentRevision=ref(0);
 const playIntent=computed(()=>{void intentRevision.value;void phase.value;return controller.desiredPlaying;});
 async function select(song:SearchEntry){clearTimeout(timer);selected.value=song;await controller.select(trackIdentity(song));}
 async function stop(){clearTimeout(timer);selected.value=null;await controller.stop();}
 let storage:Storage|undefined;try{storage=window.localStorage;}catch{/* 无存储也能播放。 */}
 const queue=useQueue(select,stop,()=>!!controller.session&&['ready','blocked'].includes(controller.phase),Math.random,storage);
 function setVolume(value:number){audio.volume=Math.max(0,Math.min(1,value));audio.muted=false;volume.value=audio.volume;muted.value=audio.muted;}
 const pagehide=()=>{void stop();};window.addEventListener('pagehide',pagehide);
 onUnmounted(()=>{disposed=true;clearTimeout(timer);window.removeEventListener('pagehide',pagehide);for(const [event,handler] of listeners)audio.removeEventListener(event,handler);void controller.dispose();audio.remove();});
 return {audio,selected,selectedId,time,duration,playing,playIntent,muted,volume,message,phase,queue,select:queue.select,stop,setVolume,
  toggle:()=>{const ended=audio.ended;if(ended)controller.seek(0);const result=controller.setPlaying(ended||!controller.desiredPlaying);intentRevision.value++;return result;},mute:()=>{audio.muted=!audio.muted;},seek:(value:number)=>controller.seek(value),retry:()=>controller.recover(false)};
}

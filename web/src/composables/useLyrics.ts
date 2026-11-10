import {computed,nextTick,onScopeDispose,ref,shallowRef,watch,type Ref} from 'vue';
import type {TrackIdentity,LyricLine} from '../types/core';
import {getLyrics} from '../api/lyrics';
import {createLyricsLoader,currentLyricIndex,type LyricsState} from '../player/lyrics-state';

export function useLyrics(identity:Ref<TrackIdentity|null>){
 const state=shallowRef<LyricsState>({document:null,loading:false,error:''});
 const loader=createLyricsLoader(getLyrics,value=>{state.value=value;});
 watch(()=>identity.value?JSON.stringify(identity.value):'',()=>{void loader.select(identity.value);},{immediate:true,flush:'sync'});
 onScopeDispose(loader.dispose);
 return {state,retry:()=>loader.select(identity.value,true)};
}

/** 沿用旧面板的三秒恢复跟随；只有用户输入暂停，程序滚动不会暂停。 */
export function useLyricPresentation(lines:Ref<readonly LyricLine[]>,time:Ref<number>){
 const viewport=ref<HTMLElement>(),following=ref(true),index=computed(()=>currentLyricIndex(lines.value,time.value));
 let timer:ReturnType<typeof setTimeout>|undefined,disposed=false;
 async function center(){await nextTick();if(disposed||!following.value)return;const box=viewport.value,line=box?.querySelector<HTMLElement>('[aria-current="true"]');if(!box||!line)return;
  box.scrollTo({top:box.scrollTop+line.getBoundingClientRect().top-box.getBoundingClientRect().top-box.clientTop-box.clientHeight/2+line.getBoundingClientRect().height/2,behavior:'auto'});
 }
 function resumeFollowing(){clearTimeout(timer);following.value=true;void center();}
 function schedule(){clearTimeout(timer);timer=setTimeout(resumeFollowing,3000);}
 function pauseFollowing(){following.value=false;schedule();}
 function onScroll(){if(!following.value)schedule();}
 function onKey(event:KeyboardEvent){if(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key))pauseFollowing();}
 watch(index,center,{flush:'post'});watch(lines,resumeFollowing,{flush:'post'});
 const observer=new ResizeObserver(()=>{void center();});
 watch(viewport,box=>{observer.disconnect();if(box)observer.observe(box);void center();},{flush:'post'});
 onScopeDispose(()=>{disposed=true;clearTimeout(timer);observer.disconnect();});
 return {viewport,index,following,pauseFollowing,resumeFollowing,onScroll,onKey,center};
}

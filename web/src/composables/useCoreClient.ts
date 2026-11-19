import {bridge,publishDesktopLyrics} from './useDesktopLyrics';
import { computed,inject,onScopeDispose,provide,ref,type InjectionKey } from 'vue';
import {useCoreSearch} from './useCoreSearch';
import {usePlayer} from '../player/usePlayer';
import {useLyrics} from './useLyrics';
import {isLocalSong} from '../types/music';
import {trackIdentity} from '../utils/player-queue';
import {useDownloads} from './useDownloads';
const key:InjectionKey<{searchState:ReturnType<typeof useCoreSearch>;player:ReturnType<typeof usePlayer>;lyrics:{state:Readonly<ReturnType<typeof useLyrics>["state"]>;retry:ReturnType<typeof useLyrics>["retry"]};downloads:ReturnType<typeof useDownloads>;coverRevision:Readonly<ReturnType<typeof ref<number>>>}>=Symbol('core-client');
export function provideCoreClient(){const player=usePlayer(),onlineLyrics=useLyrics(computed(()=>player.selected.value&&!isLocalSong(player.selected.value)?trackIdentity(player.selected.value):null));const lyrics={...onlineLyrics,state:computed(()=>player.selected.value&&isLocalSong(player.selected.value)?{document:player.localLyrics.value,loading:false,error:""}:onlineLyrics.state.value)};const coverRevision=ref(0);
 let stop: (()=>void) | undefined, disposed=false;
 void bridge?.event.listen('desktop-cached-covers-changed',()=>{coverRevision.value++;})
  .then(unlisten=>{if(disposed)unlisten();else stop=unlisten;}).catch(()=>{});
 onScopeDispose(()=>{disposed=true;stop?.();});
 const state={searchState:useCoreSearch(),player,lyrics,downloads:useDownloads(),coverRevision};publishDesktopLyrics(player,lyrics);provide(key,state);return state;}
export function useCoreClient(){const state=inject(key);if(!state)throw new Error('Core not initialized');return state;}

import {publishDesktopLyrics} from './useDesktopLyrics';
import { computed,inject,provide,type InjectionKey } from 'vue';
import {useCoreSearch} from './useCoreSearch';
import {usePlayer} from '../player/usePlayer';
import {useLyrics} from './useLyrics';
import {isLocalSong} from '../types/music';
import {trackIdentity} from '../utils/player-queue';
import {useDownloads} from './useDownloads';
const key:InjectionKey<{searchState:ReturnType<typeof useCoreSearch>;player:ReturnType<typeof usePlayer>;lyrics:{state:Readonly<ReturnType<typeof useLyrics>["state"]>;retry:ReturnType<typeof useLyrics>["retry"]};downloads:ReturnType<typeof useDownloads>}>=Symbol('core-client');
export function provideCoreClient(){const player=usePlayer(),onlineLyrics=useLyrics(computed(()=>player.selected.value&&!isLocalSong(player.selected.value)?trackIdentity(player.selected.value):null));const lyrics={...onlineLyrics,state:computed(()=>player.selected.value&&isLocalSong(player.selected.value)?{document:player.localLyrics.value,loading:false,error:""}:onlineLyrics.state.value)};const state={searchState:useCoreSearch(),player,lyrics,downloads:useDownloads()};publishDesktopLyrics(player,lyrics);provide(key,state);return state;}
export function useCoreClient(){const state=inject(key);if(!state)throw new Error('Core not initialized');return state;}

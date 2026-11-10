import { computed,inject,provide,type InjectionKey } from 'vue';
import {useCoreSearch} from './useCoreSearch';
import {usePlayer} from '../player/usePlayer';
import {useLyrics} from './useLyrics';
import {isLocalSong} from '../types/music';
import {trackIdentity} from '../utils/player-queue';
import {useDownloads} from './useDownloads';
const key:InjectionKey<{searchState:ReturnType<typeof useCoreSearch>;player:ReturnType<typeof usePlayer>;lyrics:ReturnType<typeof useLyrics>;downloads:ReturnType<typeof useDownloads>}>=Symbol('core-client');
export function provideCoreClient(){const player=usePlayer(),lyrics=useLyrics(computed(()=>player.selected.value&&!isLocalSong(player.selected.value)?trackIdentity(player.selected.value):null));const state={searchState:useCoreSearch(),player,lyrics,downloads:useDownloads()};provide(key,state);return state;}
export function useCoreClient(){const state=inject(key);if(!state)throw new Error('Core not initialized');return state;}

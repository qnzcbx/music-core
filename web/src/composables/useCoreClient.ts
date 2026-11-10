import { inject,provide,type InjectionKey } from 'vue';
import {useCoreSearch} from './useCoreSearch';
import {usePlayer} from '../player/usePlayer';
const key:InjectionKey<{searchState:ReturnType<typeof useCoreSearch>;player:ReturnType<typeof usePlayer>}>=Symbol('core-client');
export function provideCoreClient(){const state={searchState:useCoreSearch(),player:usePlayer()};provide(key,state);return state;}
export function useCoreClient(){const state=inject(key);if(!state)throw new Error('Core not initialized');return state;}

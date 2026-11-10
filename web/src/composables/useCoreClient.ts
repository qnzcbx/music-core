import { inject,provide,type InjectionKey } from 'vue';
import {useCoreSearch} from './useCoreSearch';
const key:InjectionKey<{searchState:ReturnType<typeof useCoreSearch>}>=Symbol('core-client');
export function provideCoreClient(){const state={searchState:useCoreSearch()};provide(key,state);return state;}
export function useCoreClient(){const state=inject(key);if(!state)throw new Error('Core not initialized');return state;}

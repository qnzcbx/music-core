import { computed, onUnmounted, ref, watch, type Ref } from 'vue';
import type { SearchEntry, Song } from '../types/music';
import type { Provider } from './useProviders';
import { createSongGroupState } from '../utils/song-group';

/** 根会话持有组交互状态；新搜索重置，SSE 追加及路由切换保持。 */
export function useSongGroups(songs: Ref<SearchEntry[]>, providers: Readonly<Ref<readonly Provider[]>>, active: Ref<Song | null>) {
  const state = createSongGroupState();
  const revision = ref(0), now = ref(Date.now());
  const groups = computed(() => {
    revision.value;
    return state.update(songs.value, providers.value.filter(provider => provider.enabled).map(provider => provider.id), active.value?.id, now.value, active.value ?? undefined);
  });
  watch(songs, () => { state.reset(); revision.value++; }, { flush: 'sync' });
  const timer = window.setInterval(() => { now.value = Date.now(); }, 5000);
  onUnmounted(() => clearInterval(timer));
  return { groups, now,
    lockRepresentatives() { groups.value; state.lockRepresentatives(); revision.value++; },
    toggle(key: string) { state.toggle(key); revision.value++; },
    select(song: SearchEntry) { state.select(song, groups.value); revision.value++; },
    promote(song: SearchEntry) { const promoted = state.promote(song, groups.value, Date.now()); if (promoted) revision.value++; return promoted; },
  };
}

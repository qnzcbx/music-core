import { computed, ref, watch, type Ref } from 'vue';
import type { ProviderInfo, TrackIdentity } from '../types/core';
import type { SearchEntry } from '../types/music';
import { createSongGroupState } from '../utils/song-group.ts';

/** 新搜索重置代表版本，继续分页时保留用户已展开或锁定的组。 */
export function useSongGroups(
  songs: Ref<SearchEntry[]>,
  providers: Readonly<Ref<readonly ProviderInfo[]>>,
  selected: Readonly<Ref<TrackIdentity | null>>,
) {
  const state = createSongGroupState();
  const revision = ref(0);
  const groups = computed(() => {
    void revision.value;
    return state.update(songs.value, providers.value.map((provider) => provider.id), selected.value);
  });
  watch(songs, () => { state.reset(); revision.value++; }, { flush: 'sync' });
  return {
    groups,
    lockRepresentatives() { void groups.value; state.lockRepresentatives(); },
    toggle(key: string) { state.toggle(key); revision.value++; },
  };
}

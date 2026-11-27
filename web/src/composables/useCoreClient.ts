import { computed, inject, provide, readonly, ref, type InjectionKey, type Ref } from 'vue';
import { desktopLyrics, publishDesktopLyrics } from './useDesktopLyrics';
import { listenDesktop, trackPageVisibility } from '../platform/window';
import { bindDesktopTray } from '../platform/tray';
import { usePlayer } from '../player/usePlayer';
import { isLocalSong } from '../types/music';
import { useCoreSearch } from './useCoreSearch';
import { useDownloads } from './useDownloads';
import { useLyrics } from './useLyrics';

type CoreClient = {
  searchState: ReturnType<typeof useCoreSearch>;
  player: ReturnType<typeof usePlayer>;
  lyrics: { state: Readonly<ReturnType<typeof useLyrics>['state']>; retry: ReturnType<typeof useLyrics>['retry'] };
  downloads: ReturnType<typeof useDownloads>;
  coverRevision: Readonly<Ref<number>>;
};

const key: InjectionKey<CoreClient> = Symbol('core-client');

export function provideCoreClient() {
  const player = usePlayer();
  const identity = computed(() => {
    const song = player.selected.value;
    return song && !isLocalSong(song) ? song.identity : null;
  });
  const onlineLyrics = useLyrics(identity);
  const lyrics = {
    retry: onlineLyrics.retry,
    state: computed(() => {
      const song = player.selected.value;
      return song && isLocalSong(song)
        ? { document: player.localLyrics.value, loading: false, error: '' }
        : onlineLyrics.state.value;
    }),
  };
  const coverRevision = ref(0);
  trackPageVisibility();
  void listenDesktop('desktop-cached-covers-changed', () => { coverRevision.value++; });
  bindDesktopTray(player, desktopLyrics.toggle);
  publishDesktopLyrics(player, lyrics);
  const client: CoreClient = {
    searchState: useCoreSearch(), player, lyrics, downloads: useDownloads(), coverRevision: readonly(coverRevision),
  };
  provide(key, client);
  return client;
}

export function useCoreClient() {
  const client = inject(key);
  if (!client) throw new Error('Core not initialized');
  return client;
}

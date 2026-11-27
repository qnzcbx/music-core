import { computed, onScopeDispose, readonly, ref, watch } from 'vue';
import { isLocalSong } from '../types/music';
import { dispatchDesktopPlayback, lyricChannel, lyricSnapshot, type DesktopPlayback, type Update } from '../player/desktop-lyrics';
import { bridge, readDesktopPlatform } from '../platform/desktop';
import { desktopCapabilities, listenDesktop } from '../platform/window';
import type { usePlayer } from '../player/usePlayer';
import type { useLyrics } from './useLyrics';

const open = ref(false);
const pending = ref(false);
const error = ref('');
export const desktopLyrics = {
  open: readonly(open),
  pending: readonly(pending),
  error: readonly(error),
  async toggle() {
    if (!bridge || !desktopCapabilities.value?.desktopLyrics || pending.value) return;
    pending.value = true;
    error.value = '';
    try {
      await bridge.core.invoke('toggle_desktop_lyrics');
    } catch {
      error.value = '无法打开桌面歌词，请重试';
    } finally {
      pending.value = false;
    }
  },
};

export function publishDesktopLyrics(
  player: ReturnType<typeof usePlayer>,
  lyrics: { state: Readonly<ReturnType<typeof useLyrics>['state']> },
) {
  if (!bridge) return;
  const channel = new BroadcastChannel(lyricChannel);
  const publisher = performance.timeOrigin + performance.now();
  const playback = computed<DesktopPlayback>(() => ({
    canPrevious: player.queue.hasPrevious.value,
    canNext: player.queue.hasNext.value,
    canToggle: !!player.selected.value && !player.busy.value,
    playing: player.playing.value && !player.failed.value,
    label: player.actionLabel.value,
  }));
  const data = computed(() => {
    const song = player.selected.value;
    const document = lyrics.state.value.document;
    const identity = !song ? null : isLocalSong(song) ? document?.identity ?? null : song.identity;
    return JSON.stringify(lyricSnapshot(identity, document, player.time.value));
  });
  const actions = { previous: player.queue.previous, toggle: player.toggle, next: player.queue.next };
  let sequence = 0;
  let visibilityRevision = 0;
  let disposed = false;

  function send() {
    const update: Update = {
      publisher, sequence: ++sequence, snapshot: JSON.parse(data.value), playback: { ...playback.value },
    };
    channel.postMessage(update);
  }
  channel.onmessage = ({ data }) => {
    if (data === 'snapshot') send();
    else if (open.value && data?.type === 'playback') {
      void dispatchDesktopPlayback(data.action, playback.value, actions);
    }
  };
  watch([data, playback], () => { if (open.value) send(); });
  void listenDesktop<boolean>('desktop-lyrics-visible', (visible) => {
    visibilityRevision++;
    open.value = visible;
    if (visible) send();
  }).then(async (registered) => {
    if (!registered || disposed) return;
    const revision = visibilityRevision;
    const state = await readDesktopPlatform();
    if (!state || disposed || revision !== visibilityRevision) return;
    open.value = state.lyricsVisible;
    if (open.value) send();
  }).catch(console.error);
  onScopeDispose(() => {
    disposed = true;
    channel.close();
  });
}

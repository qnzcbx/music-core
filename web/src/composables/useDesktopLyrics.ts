import { computed, onScopeDispose, readonly, ref, watch } from 'vue';
import { isDesktop } from '../api/transport';
import { isLocalSong } from '../types/music';
import { trackIdentity } from '../utils/player-queue';
import { dispatchDesktopPlayback, lyricSnapshot, type DesktopPlayback, type Update } from '../player/desktop-lyrics';
import type { usePlayer } from '../player/usePlayer';
import type { useLyrics } from './useLyrics';

type Bridge = {
  core: { invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> };
  event: { listen<T>(name: string, handler: (event: {payload: T}) => void): Promise<() => void> };
};
export const bridge = (window as Window & { __TAURI__?: Bridge }).__TAURI__;
export const hasWindowsTray = isDesktop && /Windows/.test(navigator.userAgent);
const mainHidden = ref(false);
export const desktopMainHidden = readonly(mainHidden);
export const lyricChannel = 'musiccore:desktop-lyrics:v1';
const open = ref(false), pending = ref(false), error = ref('');
export const desktopLyrics = { open: readonly(open), pending: readonly(pending), error: readonly(error), async toggle() {
  if (!bridge || pending.value) return;
  pending.value = true;
  error.value = '';
  try { await bridge.core.invoke('toggle_desktop_lyrics'); }
  catch { error.value = '无法打开桌面歌词，请重试'; }
  finally { pending.value = false; }
} };

export function publishDesktopLyrics(player: ReturnType<typeof usePlayer>, lyrics: {state: Readonly<ReturnType<typeof useLyrics>["state"]>}) {
  if (!isDesktop || !bridge) return;
  const channel = new BroadcastChannel(lyricChannel);
  const playback = computed<DesktopPlayback>(() => ({
    canPrevious: player.queue.hasPrevious.value,
    canNext: player.queue.hasNext.value,
    canToggle: !!player.selected.value && !player.busy.value,
    playing: player.playing.value && !player.failed.value,
    label: player.actionLabel.value,
  }));
  const data = computed(() => {
    const song = player.selected.value;
    return JSON.stringify(lyricSnapshot(song ? isLocalSong(song) ? lyrics.state.value.document?.identity ?? null : trackIdentity(song) : null,
      lyrics.state.value.document, player.time.value));
  });
  let sequence = 0, disposed = false;
  const unlisteners: (() => void)[] = [];
  const actions = { previous: player.queue.previous, toggle: player.toggle, next: player.queue.next };
  const ipc = bridge;
  async function listen<T>(name: string, handler: (event: { payload: T }) => void) {
    try {
      const stop = await ipc.event.listen<T>(name, handler);
      if (disposed) stop();
      else unlisteners.push(stop);
      return !disposed;
    } catch (error) {
      console.error(error);
      return false;
    }
  }
  function send() {
    const update: Update = { sequence: ++sequence, snapshot: JSON.parse(data.value), playback: { ...playback.value } };
    channel.postMessage(update);
  }
  channel.onmessage = ({data}) => {
    if (data === 'snapshot') send();
    else if (open.value && data?.type === 'playback') {
      void dispatchDesktopPlayback(data.action, playback.value, actions);
    }
  };
  watch([data, playback], () => { if (open.value) send(); });
  void listen<boolean>('desktop-lyrics-visible', ({payload}) => {
    open.value = payload;
    if (payload) send();
  });
  if (hasWindowsTray) {
    // 注册完成后才启用托盘播放菜单，避免启动阶段点击丢失。
    const ready = ref(false);
    void listen<unknown>('desktop-tray-action', ({ payload }) => {
      if (payload === 'lyrics') void desktopLyrics.toggle();
      else void dispatchDesktopPlayback(payload, playback.value, actions);
    }).then(registered => { if (!disposed) ready.value = registered; });
    void listen<boolean>('desktop-main-hidden', ({ payload }) => { mainHidden.value = payload; });
    watch([
      ready,
      () => playback.value.canPrevious,
      () => playback.value.canToggle,
      () => playback.value.canNext,
      () => playback.value.playing,
    ], ([enabled, canPrevious, canToggle, canNext, playing]) => {
      if (!enabled) return;
      void ipc.core.invoke('desktop_tray_playback', {
        playback: { canPrevious, canToggle, canNext, playing },
      }).catch(console.error);
    });
  }
  onScopeDispose(() => {
    disposed = true;
    unlisteners.forEach(stop => stop());
    channel.close();
  });
}

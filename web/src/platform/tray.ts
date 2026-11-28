import { computed, ref, watch } from 'vue';
import type { usePlayer } from '../player/usePlayer';
import { dispatchDesktopPlayback } from '../player/desktop-lyrics';
import { bridge } from './desktop';
import { desktopCapabilities, listenDesktop } from './window';

export function bindDesktopTray(player: ReturnType<typeof usePlayer>, toggleLyrics: () => unknown) {
  const ipc = bridge;
  if (!ipc) return;
  const ready = ref(false);
  const playback = computed(() => ({
    canPrevious: player.queue.hasPrevious.value,
    canNext: player.queue.hasNext.value,
    canToggle: !!player.selected.value && !player.busy.value,
    playing: player.playing.value && !player.failed.value,
  }));
  const actions = { previous: player.queue.previous, next: player.queue.next, toggle: player.toggle };
  void listenDesktop<unknown>('desktop-tray-action', (action) => {
    if (!desktopCapabilities.value?.tray) return;
    if (action === 'lyrics') void toggleLyrics();
    else void dispatchDesktopPlayback(action, playback.value, actions);
  }).then((registered) => { ready.value = registered; });
  watch([ready, () => desktopCapabilities.value?.tray, playback], ([listening, tray, state]) => {
    if (listening && tray) {
      void ipc.core.invoke('desktop_tray_playback', { playback: state }).catch(console.error);
    }
  });
}

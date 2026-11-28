import type { LyricDocument } from '../types/core';
import { computed, onUnmounted, ref, shallowRef, watch } from 'vue';
import { useStorage } from '@vueuse/core';
import { RecoveryPlayer } from './recovery-player.mjs';
import { invokeCore } from '../api/transport';
import { closePlayback, openLocalPlayback, playbackOperations } from '../api/playback';
import { isDesktop } from '../platform/desktop';
import { isLocalSong, type PlayableSong } from '../types/music';
import { localStreamUrl, listDownloadFiles } from '../api/downloads';
import type { SavedDownloadFile, DownloadTask } from '../types/core';
import { trackIdentity } from '../utils/player-queue';
import { useQueue } from './useQueue';

/** 根提供者创建一次，路由页面不拥有音频或续期任务。 */
export function usePlayer() {
  const audio = document.createElement('audio');
  audio.preload = 'metadata';
  audio.hidden = true;
  const localLyrics = shallowRef<LyricDocument | null>(null);
  const selected = shallowRef<PlayableSong | null>(null),
    time = ref(0),
    duration = ref(0),
    playing = ref(false),
    message = ref('选择歌曲开始播放'),
    phase = ref('idle'),
    muted = ref(false);
  const volume = useStorage('music-core.volume.v1', 1);
  audio.volume = Math.max(0, Math.min(1, Number(volume.value) || 0));
  let timer: ReturnType<typeof setTimeout> | undefined,
    disposed = false,
    selectionRevision = 0;
  let restored = false,
    leaving = false;
  let localAbort: AbortController | undefined;
  let desktopLocalSession: string | undefined;
  function closeDesktopLocal(id = desktopLocalSession) {
    if (!id) return;
    if (desktopLocalSession === id) desktopLocalSession = undefined;
    return closePlayback(id).catch(() => {});
  }
  const localIntent = ref(false);
  const local = computed(() => !!selected.value && isLocalSong(selected.value));
  let scheduledSession: typeof controller.session = null;
  function schedule() {
    const session = controller.session;
    if (!session || disposed || local.value) return;
    if (timer !== undefined && scheduledSession === session) return;
    clearTimeout(timer);
    scheduledSession = session;
    timer = setTimeout(
      async () => {
        timer = undefined;
        await controller.renew();
        if (controller.session === session) schedule();
      },
      Math.max(100, session.expiresInSeconds * 500),
    );
  }
  const controller = new RecoveryPlayer(audio, {
    operations: playbackOperations,
    notify: (state) => {
      if (local.value) return;
      phase.value = state.phase;
      message.value = state.message;
      if (state.phase === 'opening') {
        clearTimeout(timer);
        timer = undefined;
      }
      if (state.phase === 'ready' || state.phase === 'blocked') {
        sync();
        schedule();
      }
      if (state.phase === 'idle') clearTimeout(timer);
    },
  });
  const listeners: [string, EventListener][] = [];
  function listen(event: string, handler: () => void) {
    audio.addEventListener(event, handler);
    listeners.push([event, handler]);
  }
  function sync() {
    if (restored || !audio.getAttribute('src') || ['opening', 'positioning'].includes(phase.value)) {
      playing.value = false;
      return;
    }
    time.value = Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
    duration.value = Number.isFinite(audio.duration) ? audio.duration : 0;
    playing.value = !audio.paused && !audio.ended;
  }
  for (const event of [
    'loadedmetadata',
    'durationchange',
    'timeupdate',
    'seeking',
    'seeked',
    'playing',
    'pause',
    'ended',
    'emptied',
  ])
    listen(event, sync);
  listen('volumechange', () => {
    volume.value = audio.volume;
    muted.value = audio.muted;
  });
  listen('waiting', () => {
    message.value = '正在缓冲';
  });
  listen('playing', () => {
    message.value = '正在播放';
    if (local.value) phase.value = 'ready';
  });
  listen('error', () => {
    if (local.value) {
      phase.value = 'error';
      localIntent.value = false;
      message.value = '本地文件无法读取、已变化或格式不支持，请刷新下载列表';
    }
  });
  listen('ended', () => {
    if (!selected.value || !audio.ended) return;
    message.value = '播放结束';
    if (queue.navigation.mode === 'repeat_one' && selected.value) {
      seek(0);
      void setPlaying(true);
    } else void queue.advance(true);
  });
  const selectedId = computed(() => selected.value?.id);
  const busy = computed(() => ['opening', 'positioning'].includes(phase.value));
  const failed = computed(() => ['error', 'network'].includes(phase.value));
  const actionLabel = computed(() =>
    busy.value ? '正在加载' : failed.value ? '重新尝试播放' : playing.value ? '暂停' : '播放',
  );
  const intentRevision = ref(0);
  const playIntent = computed(() => {
    void intentRevision.value;
    void phase.value;
    return local.value ? localIntent.value : controller.desiredPlaying;
  });
  async function select(song: PlayableSong, startAt = 0) {
    restored = false;
    localAbort?.abort();
    closeDesktopLocal();
    time.value = startAt;
    duration.value = Number(song.duration) || 0;
    phase.value = 'opening';
    const revision = ++selectionRevision;
    clearTimeout(timer);
    timer = undefined;
    localLyrics.value = null;
    selected.value = isDesktop && !isLocalSong(song) ? {...song, cover:null} : song;
    if (!isLocalSong(song)) {
      localIntent.value = false;
      const identity = trackIdentity(song);
      if (isDesktop) {
        void invokeCore<{ cover: string | null }>({
          op: 'cachedCover', payload: { identity, cover: song.cover },
        }, { timeoutMs: 20_000 }).then(({cover}) => {
          if (revision === selectionRevision && !disposed) selected.value = {...song, cover:cover ?? song.cover};
        }).catch(() => {
          if (revision === selectionRevision && !disposed) selected.value = song;
        });
      }
      await controller.select(identity, startAt);
      return;
    }
    phase.value = 'opening';
    message.value = '正在打开本地文件';
    localIntent.value = true;
    await controller.stop();
    if (revision !== selectionRevision || disposed) return;
    localAbort = new AbortController();
    const signal = localAbort.signal;
    try {
      if (isDesktop) {
        const session = await openLocalPlayback(song.fileId);
        if (revision !== selectionRevision || disposed || signal.aborted) {
          closeDesktopLocal(session.playbackId);
          return;
        }
        desktopLocalSession = session.playbackId;
        audio.src = session.streamUrl;
        localLyrics.value = session.lyrics ?? null;
        if (session.cover) selected.value = {...song, cover: session.cover};
      } else {
        const files = await listDownloadFiles(signal);
        if (revision !== selectionRevision || disposed) return;
        if (!files.some((file) => file.fileId === song.fileId)) {
          throw new Error('本地文件已不存在，请刷新下载列表');
        }
        audio.src = localStreamUrl(song.fileId);
      }
      audio.load();
      await controller.waitMedia(
        () => audio.readyState >= 1 && Number.isFinite(audio.duration),
        ['loadedmetadata', 'durationchange'],
        signal,
      );
      if (revision !== selectionRevision || disposed) return;
      phase.value = 'positioning';
      const target = Math.max(0, Math.min(startAt, Math.max(0, audio.duration - 0.1)));
      audio.currentTime = target;
      await controller.waitMedia(
        () => !audio.seeking && Math.abs(audio.currentTime - target) <= 0.5,
        ['seeked', 'canplay', 'timeupdate'],
        signal,
      );
      if (revision !== selectionRevision || disposed) return;
    } catch (reason) {
      if (revision !== selectionRevision || disposed) return;
      closeDesktopLocal();
      phase.value = 'error';
      message.value = isDesktop && reason instanceof Error ? reason.message : '本地文件无法读取，请刷新下载列表';
      localIntent.value = false;
      return;
    }
    phase.value = 'ready';
    sync();
    if (!localIntent.value) {
      phase.value = 'ready';
      message.value = '已暂停';
      return;
    }
    try {
      await audio.play();
      if (revision === selectionRevision) {
        phase.value = 'ready';
        message.value = '正在播放';
      }
    } catch (reason) {
      if (revision !== selectionRevision) return;
      if (reason instanceof DOMException && reason.name === 'AbortError' && !localIntent.value) {
        phase.value = 'ready';
        message.value = '已暂停';
      } else if (reason instanceof DOMException && reason.name === 'NotAllowedError') {
        phase.value = 'blocked';
        message.value = '点击播放本地文件';
      } else {
        phase.value = 'error';
        localIntent.value = false;
        message.value = '本地文件无法读取、已变化或格式不支持，请刷新下载列表';
      }
    }
  }
  async function stop() {
    restored = false;
    localAbort?.abort();
    const closing = closeDesktopLocal();
    selectionRevision++;
    clearTimeout(timer);
    timer = undefined;
    localLyrics.value = null;
    selected.value = null;
    time.value = 0;
    duration.value = 0;
    playing.value = false;
    localIntent.value = false;
    await Promise.all([controller.stop(), closing]);
  }

  async function releaseLocalForRecycle(fileId: string) {
    const song = selected.value;
    if (!song || !isLocalSong(song) || song.fileId !== fileId) return;
    const snapshot = { position: time.value, duration: duration.value };
    const stopped = stop();
    const revision = selectionRevision;
    await stopped;
    return () => {
      if (selectionRevision !== revision || disposed) return;
      selected.value = song;
      time.value = snapshot.position;
      duration.value = snapshot.duration;
      restored = true;
      phase.value = 'ready';
      queue.position.value = snapshot.position;
      message.value = '已暂停';
    };
  }

  function seek(value: number) {
    if (!Number.isFinite(value)) return;
    if (restored) {
      time.value = Math.max(0, value);
      queue.position.value = time.value;
      return;
    }
    if (local.value) {
      if (Number.isFinite(audio.duration))
        audio.currentTime = Math.max(0, Math.min(value, audio.duration));
    } else controller.seek(value);
  }
  async function setPlaying(value: boolean) {
    if (!local.value) return controller.setPlaying(value);
    const revision = selectionRevision;
    localIntent.value = value;
    if (!value) {
      audio.pause();
      return;
    }
    try {
      await audio.play();
    } catch {
      if (revision !== selectionRevision) return;
      message.value = '本地文件无法播放，请刷新列表后重试';
      phase.value = 'error';
      localIntent.value = false;
    }
  }
  let storage: Storage | undefined;
  try {
    storage = window.localStorage;
  } catch {
    /* 无存储也能播放。 */
  }
  const queue = useQueue(
    select,
    stop,
    () =>
      local.value
        ? ['ready', 'blocked'].includes(phase.value)
        : !!controller.session && ['ready', 'blocked'].includes(controller.phase),
    Math.random,
    storage,
  );
  // 只恢复展示，不触碰媒体入口或Lease；首次点击才真正打开。
  if (queue.currentSong.value) {
    selected.value = queue.currentSong.value;
    time.value = queue.position.value;
    duration.value = Number(selected.value.duration) || 0;
    phase.value = 'ready';
    message.value = '已暂停';
    restored = true;
  }
  let lastSaved = 0;
  function save(force = false) {
    if (leaving || disposed || !selected.value || ['opening', 'positioning'].includes(phase.value))
      return;
    const now = performance.now();
    if (!force && now - lastSaved < 2000) return;
    lastSaved = now;
    const entry = queue.entries.value.find((item) => item.key === queue.current.value);
    if (!restored && entry && duration.value > 0) entry.metadata.durationSeconds = duration.value;
    queue.position.value = audio.ended ? 0 : Math.max(0, time.value);
  }
  for (const event of ['timeupdate', 'pause', 'seeked', 'ended'])
    listen(event, () => save(event !== 'timeupdate'));
  watch(
    [() => queue.entries.value.map((entry) => entry.key).join(), () => queue.navigation.mode],
    () => save(true),
  );
  const visibility = () => {
    if (document.hidden) save(true);
  };
  document.addEventListener('visibilitychange', visibility);

  function setVolume(value: number) {
    audio.volume = Math.max(0, Math.min(1, value));
    audio.muted = false;
    volume.value = audio.volume;
    muted.value = audio.muted;
  }
  const pagehide = () => {
    save(true);
    leaving = true;
    restored = !!selected.value;
    localAbort?.abort();
    closeDesktopLocal();
    void controller.stop();
  };
  window.addEventListener('pagehide', pagehide);
  const pageshow = () => {
    leaving = false;
    if (restored) {
      time.value = queue.position.value;
      playing.value = false;
      phase.value = 'ready';
      message.value = '已暂停';
    }
  };
  window.addEventListener('pageshow', pageshow);
  onUnmounted(() => {
    save(true);
    disposed = true;
    localAbort?.abort();
    closeDesktopLocal();
    document.removeEventListener('visibilitychange', visibility);
    clearTimeout(timer);
    window.removeEventListener('pagehide', pagehide);
    window.removeEventListener('pageshow', pageshow);
    for (const [event, handler] of listeners) audio.removeEventListener(event, handler);
    void controller.dispose();
    audio.remove();
  });
  return {
    audio,
    selected,
    localLyrics,
    selectedId,
    time,
    duration,
    playing,
    playIntent,
    busy,
    failed,
    actionLabel,
    muted,
    volume,
    message,
    phase,
    queue,
    select: queue.select,
    stop,
    setVolume,
    selectLocal: (file: SavedDownloadFile, task?: DownloadTask) =>
      queue.select({
        kind: 'local',
        fileId: file.fileId,
        id: JSON.stringify(['local', file.fileId]),
        title: file.title || task?.title || file.filename,
        artist: file.artist || task?.artist || '',
        album: file.album || '',
        cover: file.cover || null,
        duration: null,
      }),
    releaseLocalForRecycle,
    removeLocal: (fileId: string) => queue.remove(JSON.stringify(['local', fileId])),
    toggle: () => {
      if (!selected.value || busy.value) return;
      if (restored) return select(selected.value, time.value);
      if (failed.value) {
        intentRevision.value++;
        return local.value ? select(selected.value, time.value) : controller.setPlaying(true);
      }
      const ended = audio.ended;
      if (ended) seek(0);
      const result = setPlaying(ended || !playIntent.value);
      intentRevision.value++;
      return result;
    },
    mute: () => {
      audio.muted = !audio.muted;
    },
    seek,
    retry: () =>
      local.value && selected.value ? select(selected.value) : controller.recover(false),
  };
}

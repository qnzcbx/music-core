import { computed, reactive, ref, watch } from 'vue';
import type { PlayableQueueEntry, PlayableSong } from '../types/music.ts';
import { isLocalSong } from '../types/music.ts';
import { queueEntryFrom } from '../utils/player-queue.ts';
import { createQueueNavigation, type PlaybackMode, type QueueStep } from './queue-navigation.ts';
import { decodePlayer, encodePlayer, MAX_QUEUE } from './player-persistence.ts';

/** 只管理稳定歌曲和导航；媒体生命周期仍由已有播放器负责。 */
export function useQueue(
  open: (song: PlayableSong) => Promise<void>,
  stop: () => Promise<void>,
  successful: () => boolean,
  random = Math.random,
  storage: Pick<Storage, 'getItem' | 'setItem'> | undefined = undefined,
) {
  const entries = ref<PlayableQueueEntry[]>([]),
    current = ref<string | null>(null),
    navigation = reactive(createQueueNavigation(random));
  const position = ref(0);
  const storageKey = 'music-core.queue.v1';
  try {
    const saved = decodePlayer(storage?.getItem(storageKey) ?? null);
    if (saved.kind === 'valid') {
      position.value = saved.value.position;
      entries.value = saved.value.queue;
      current.value = saved.value.currentQueueKey;
      Object.assign(navigation, saved.value.navigation);
      navigation.knownKeys = entries.value.map((e) => e.key);
      navigation.sync(navigation.knownKeys, current.value);
    }
  } catch {
    /* 存储不可用时保留本次页面队列。 */
  }
  const entryFrom = (song: PlayableSong): PlayableQueueEntry =>
    isLocalSong(song)
      ? {
          key: JSON.stringify(['local', song.fileId]),
          kind: 'local',
          fileId: song.fileId,
          metadata: {
            title: song.title,
            artist: song.artist,
            album: song.album,
            cover: song.cover,
            durationSeconds: song.duration,
          },
        }
      : queueEntryFrom(song);
  const keys = () => entries.value.map((e) => e.key);
  function sync() {
    navigation.sync(keys(), current.value);
  }
  function add(song: PlayableSong) {
    const entry = entryFrom(song),
      held = entries.value.find((e) => e.key === entry.key);
    if (held) {
      held.metadata = entry.metadata;
      return held;
    }
    if (entries.value.length >= MAX_QUEUE) return;
    entries.value.push(entry);
    sync();
    return entry;
  }
  function row(entry: PlayableQueueEntry): PlayableSong {
    if ('kind' in entry)
      return {
        kind: 'local',
        fileId: entry.fileId,
        id: entry.key,
        source: 'local',
        title: entry.metadata.title,
        name: entry.metadata.title,
        artist: entry.metadata.artist,
        album: entry.metadata.album,
        cover: entry.metadata.cover,
        duration: entry.metadata.durationSeconds,
      };
    return {
      identity: entry.track,
      id: entry.key,
      source: entry.track.providerId,
      platformId: entry.track.platformId,
      mid: entry.track.platformId,
      title: entry.metadata.title,
      name: entry.metadata.title,
      artist: entry.metadata.artist,
      album: entry.metadata.album,
      duration: entry.metadata.durationSeconds,
      cover: entry.metadata.cover,
      resolveState: 'idle',
    };
  }
  async function choose(entry: PlayableQueueEntry, step?: QueueStep) {
    current.value = entry.key;
    sync();
    await open(row(entry));
    if (
      current.value === entry.key &&
      entries.value.some((e) => e.key === entry.key) &&
      successful()
    )
      navigation.visit(entry.key, step?.historyIndex);
  }
  async function select(song: PlayableSong) {
    const entry = add(song);
    if (entry) await choose(entry);
  }
  async function advance(ended = false) {
    const step = navigation.next(keys(), current.value, ended);
    if (!step) return;
    const entry = entries.value.find((e) => e.key === step.key);
    if (entry) await choose(entry, step);
  }
  async function previous() {
    const step = navigation.previous(current.value),
      entry = entries.value.find((e) => e.key === step?.key);
    if (step && entry) await choose(entry, step);
  }
  async function remove(key: string) {
    entries.value = entries.value.filter((e) => e.key !== key);
    if (current.value === key) {
      current.value = null;
      await stop();
    }
    sync();
  }
  function clearPending() {
    entries.value = entries.value.filter((e) => e.key === current.value);
    sync();
  }
  async function clear() {
    entries.value = [];
    current.value = null;
    navigation.reset();
    await stop();
  }
  function setMode(mode: PlaybackMode) {
    navigation.setMode(mode, keys(), current.value);
  }
  watch(
    current,
    () => {
      position.value = 0;
    },
    { flush: 'sync' },
  );
  watch(
    [entries, current, navigation, position],
    () => {
      try {
        storage?.setItem(
          storageKey,
          encodePlayer({
            queue: entries.value,
            currentQueueKey: current.value,
            navigation,
            volume: 1,
            position: position.value,
          }),
        );
      } catch {
        /* 不因配额或隐私模式中断播放。 */
      }
    },
    { deep: true, flush: 'sync' },
  );
  return {
    entries,
    current,
    navigation,
    position,
    currentSong: computed(() => {
      const entry = entries.value.find((e) => e.key === current.value);
      return entry ? row(entry) : null;
    }),
    add,
    select,
    choose,
    remove,
    clearPending,
    clear,
    setMode,
    next: () => advance(false),
    advance,
    previous,
    hasNext: computed(() => !!navigation.preview(keys(), current.value, false)),
    hasPrevious: computed(() => !!navigation.previous(current.value)),
    key: (song: PlayableSong) => entryFrom(song).key,
  };
}

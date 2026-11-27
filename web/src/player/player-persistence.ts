import type { QueueEntry, PlayableQueueEntry } from '../types/music';
import type { PlaybackMode } from './queue-navigation.ts';
import { queueKey } from '../utils/player-queue.ts';

const SCHEMA_VERSION = 3;
export const MAX_QUEUE = 200;
const MAX_HISTORY = 1000,
  MAX_STORAGE_LENGTH = 1_000_000;
const providers = new Set(['netease', 'kuwo', 'qq', 'migu']);
const modes = new Set(['order', 'shuffle', 'repeat_all', 'repeat_one']);
type ObjectValue = Record<string, unknown>;
const object = (value: unknown): ObjectValue =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as ObjectValue)
    : {};
const text = (value: unknown, fallback = '', limit = 200) =>
  typeof value === 'string'
    ? value.replace(/[\u0000-\u001f\u007f]/g, '').slice(0, limit) || fallback
    : fallback;
function cover(value: unknown, online = false): string | null {
  if (typeof value !== 'string' || value.length > 2048) return null;
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    // Desktop relay URLs belong to one process; keep online queue entries without stale art.
    if (['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) && (url.pathname.startsWith('/cached-covers/') || (online && url.pathname.startsWith('/covers/'))))
      return null;
    let credential = false;
    url.searchParams.forEach((_value, key) => {
      if (/cookie|auth|token|signature|headers|^sign$|^key$/i.test(key)) credential = true;
    });
    if (credential) return null;
    if (/\/api\/(stream|media|resolve)|\.(mp3|flac|wav|m4a|ogg|m3u8)(?:$|\?)/i.test(url.pathname))
      return null;
    return url.href;
  } catch {
    return null;
  }
}
interface PersistedPlayer {
  schemaVersion: 3;
  queue: PlayableQueueEntry[];
  currentQueueKey: string | null;
  navigation: {
    mode: PlaybackMode;
    bag: string[];
    history: string[];
    historyIndex: number;
    upNextKeys: string[];
  };
  position: number;
  settings: { volume: number };
}
interface PersistentPlayerState {
  queue: PlayableQueueEntry[];
  currentQueueKey: string | null;
  volume: number;
  position?: number;
  navigation: PersistedPlayer['navigation'];
}
function normalize(input: ObjectValue): PersistedPlayer {
  const queue: PlayableQueueEntry[] = [],
    seen = new Set<string>();
  for (const value of (Array.isArray(input.queue) ? input.queue : []).slice(0, MAX_QUEUE)) {
    const row = object(value),
      track = object(row.track),
      meta = object(row.metadata);
    if (row.kind === 'local') {
      if (typeof row.fileId !== 'string' || !/^[a-f0-9]{64}$/.test(row.fileId)) continue;
      const key = JSON.stringify(['local', row.fileId]);
      if (seen.has(key)) continue;
      seen.add(key);
      queue.push({
        key,
        kind: 'local',
        fileId: row.fileId,
        metadata: {
          title: text(meta.title, '本地文件'),
          artist: text(meta.artist),
          album: text(meta.album),
          cover: cover(meta.cover),
          durationSeconds:
            typeof meta.durationSeconds === 'number' &&
            Number.isFinite(meta.durationSeconds) &&
            meta.durationSeconds >= 0 &&
            meta.durationSeconds <= 86400
              ? meta.durationSeconds
              : null,
        },
      });
      continue;
    }
    if (
      typeof track.providerId !== 'string' ||
      !providers.has(track.providerId) ||
      typeof track.platformId !== 'string' ||
      !/^[A-Za-z0-9_-]{1,128}$/.test(track.platformId)
    )
      continue;
    if (track.providerId === 'qq' && !/^[A-Za-z0-9]{1,64}$/.test(track.platformId)) continue;
    if (
      ['netease', 'kuwo'].includes(track.providerId) &&
      !/^[1-9][0-9]{0,19}$/.test(track.platformId)
    )
      continue;
    if (track.providerId === 'migu' && !/^[1-9][0-9]{0,31}$/.test(track.platformId)) continue;
    const identity = {
        providerId: track.providerId as QueueEntry['track']['providerId'],
        platformId: track.platformId,
      },
      key = queueKey(identity);
    if (seen.has(key)) continue;
    seen.add(key);
    queue.push({
      key,
      track: identity,
      metadata: {
        title: text(meta.title, '未命名歌曲'),
        artist: text(meta.artist, '未知歌手'),
        album: text(meta.album),
        durationSeconds:
          typeof meta.durationSeconds === 'number' &&
          Number.isFinite(meta.durationSeconds) &&
          meta.durationSeconds >= 0 &&
          meta.durationSeconds <= 86400
            ? meta.durationSeconds
            : null,
        cover: cover(meta.cover, true),
      },
    });
  }
  const nav = object(input.navigation),
    settings = object(input.settings);
  const rawHistory = Array.isArray(nav.history) ? nav.history : [],
    offset = Math.max(0, rawHistory.length - MAX_HISTORY);
  const rawIndex =
    typeof nav.historyIndex === 'number' && Number.isInteger(nav.historyIndex)
      ? Math.min(rawHistory.length - 1, Math.max(-1, nav.historyIndex))
      : -1;
  const history: string[] = [];
  let historyIndex = -1;
  rawHistory.slice(offset).forEach((key, index) => {
    if (typeof key === 'string' && seen.has(key)) {
      history.push(key);
      if (index + offset <= rawIndex) historyIndex = history.length - 1;
    }
  });
  const bag = [
    ...new Set(
      (Array.isArray(nav.bag) ? nav.bag : [])
        .slice(0, MAX_QUEUE)
        .filter((key): key is string => typeof key === 'string' && seen.has(key)),
    ),
  ];
  const upNextKeys = [
    ...new Set(
      (Array.isArray(nav.upNextKeys) ? nav.upNextKeys : [])
        .slice(0, MAX_QUEUE)
        .filter((key): key is string => typeof key === 'string' && seen.has(key)),
    ),
  ];
  return {
    schemaVersion: SCHEMA_VERSION,
    queue,
    position:
      typeof input.position === 'number' &&
      Number.isFinite(input.position) &&
      input.position >= 0 &&
      input.position <= 86400
        ? input.position
        : 0,
    currentQueueKey:
      typeof input.currentQueueKey === 'string' && seen.has(input.currentQueueKey)
        ? input.currentQueueKey
        : null,
    navigation: {
      mode:
        typeof nav.mode === 'string' && modes.has(nav.mode) ? (nav.mode as PlaybackMode) : 'order',
      bag,
      history,
      historyIndex,
      upNextKeys,
    },
    settings: {
      volume:
        typeof settings.volume === 'number' &&
        Number.isFinite(settings.volume) &&
        settings.volume >= 0 &&
        settings.volume <= 1
          ? settings.volume
          : 1,
    },
  };
}
/** Explicit projection: never traverse or stringify resolved, promises or credentials. */
export function encodePlayer(state: PersistentPlayerState): string {
  return JSON.stringify(
    normalize({
      queue: state.queue.slice(0, MAX_QUEUE).map((entry) => ({
        ...('kind' in entry
          ? { kind: 'local', fileId: entry.fileId }
          : { track: { providerId: entry.track.providerId, platformId: entry.track.platformId } }),
        metadata: {
          title: entry.metadata.title,
          artist: entry.metadata.artist,
          album: entry.metadata.album,
          durationSeconds: entry.metadata.durationSeconds,
          cover: entry.metadata.cover,
        },
      })),
      currentQueueKey: state.currentQueueKey,
      navigation: {
        mode: state.navigation.mode,
        bag: state.navigation.bag,
        history: state.navigation.history,
        historyIndex: state.navigation.historyIndex,
        upNextKeys: state.navigation.upNextKeys,
      },
      position: state.position ?? 0,
      settings: { volume: state.volume },
    }),
  );
}
export function decodePlayer(
  raw: string | null,
): { kind: 'empty' | 'invalid' | 'unsupported' } | { kind: 'valid'; value: PersistedPlayer } {
  if (raw === null) return { kind: 'empty' };
  if (raw.length > MAX_STORAGE_LENGTH) return { kind: 'invalid' };
  try {
    const input = object(JSON.parse(raw));
    if (input.schemaVersion !== SCHEMA_VERSION) return { kind: 'unsupported' };
    return { kind: 'valid', value: normalize(input) };
  } catch {
    return { kind: 'invalid' };
  }
}

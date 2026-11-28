import type { TrackIdentity } from './core';

export type { TrackIdentity } from './core';

/** 搜索候选尚未建立播放会话，下载可用性来自来源证据。 */
export interface SearchEntry {
  identity: TrackIdentity;
  id: string;
  title: string;
  artist: string;
  album: string;
  duration: number | null;
  cover: string | null;
  downloadAllowed?: boolean | null;
}

export interface TrackSnapshot {
  title: string;
  artist: string;
  album: string;
  durationSeconds: number | null;
  cover: string | null;
}

export interface QueueEntry {
  key: string;
  track: TrackIdentity;
  metadata: TrackSnapshot;
}

/** 本地条目使用独立的稳定文件引用。 */
export interface LocalSong {
  kind: 'local';
  fileId: string;
  id: string;
  title: string;
  artist: string;
  album: string;
  cover: string | null;
  duration: number | null;
}

export type PlayableSong = SearchEntry | LocalSong;
export interface LocalQueueEntry {
  key: string;
  kind: 'local';
  fileId: string;
  metadata: TrackSnapshot;
}
export type PlayableQueueEntry = QueueEntry | LocalQueueEntry;
export const isLocalSong = (song: PlayableSong): song is LocalSong =>
  'kind' in song && song.kind === 'local';

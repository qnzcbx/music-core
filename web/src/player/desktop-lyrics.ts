import type { LyricDocument, TrackIdentity } from '../types/core';
import { currentLyricIndex } from './lyrics-state.ts';

export function lyricSnapshot(identity: TrackIdentity | null, document: LyricDocument | null, time: number) {
  const lines = identity && document?.identity.providerId === identity.providerId &&
    document.identity.platformId === identity.platformId && document.status === 'synced' ? document.lines ?? [] : [];
  const index = currentLyricIndex(lines, time);
  const next = index >= 0 ? lines[index + 1] : lines.find(line => line.startMs > time * 1000);
  return { identity, current: lines[index]?.text ?? '', next: next?.text ?? '', available: lines.length > 0 };
}

export const lyricChannel = 'musiccore:desktop-lyrics:v1';

export type Snapshot = ReturnType<typeof lyricSnapshot>;
export type Update = { publisher: number; sequence: number; snapshot: Snapshot; playback?: DesktopPlayback };
export function acceptSnapshot(current: Update, incoming: Update) {
  return incoming.publisher > current.publisher ||
    (incoming.publisher === current.publisher && incoming.sequence > current.sequence)
    ? incoming : current;
}

export type PlaybackAction = 'previous' | 'toggle' | 'next';
export type DesktopPlayback = {
  canPrevious: boolean; canToggle: boolean; canNext: boolean; playing: boolean; label: string;
};

export function dispatchDesktopPlayback(action: unknown, state: Pick<DesktopPlayback, 'canPrevious' | 'canToggle' | 'canNext'>,
  actions: Record<PlaybackAction, () => unknown>) {
  if (action === 'previous' && state.canPrevious) return actions.previous();
  if (action === 'toggle' && state.canToggle) return actions.toggle();
  if (action === 'next' && state.canNext) return actions.next();
}

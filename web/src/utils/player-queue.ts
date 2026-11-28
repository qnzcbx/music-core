import type { QueueEntry, SearchEntry, TrackIdentity } from '../types/music';

export const queueKey = (track: TrackIdentity) =>
  JSON.stringify([track.providerId, track.platformId]);

export function isTrackIdentity(value: unknown): value is TrackIdentity {
  if (typeof value !== 'object' || value === null) return false;
  const { providerId, platformId } = value as Record<string, unknown>;
  if (typeof platformId !== 'string') return false;
  switch (providerId) {
    case 'qq': return /^[A-Za-z0-9]{1,64}$/.test(platformId);
    case 'kuwo':
    case 'netease': return /^[1-9][0-9]{0,19}$/.test(platformId);
    case 'migu': return /^[1-9][0-9]{0,31}$/.test(platformId);
    default: return false;
  }
}

export function trackIdentity({ identity }: SearchEntry): TrackIdentity {
  if (!isTrackIdentity(identity)) {
    throw new Error('此记录缺少可信歌曲身份，请重新搜索并选择具体版本');
  }
  const { providerId, platformId } = identity;
  return { providerId, platformId };
}

export function queueEntryFrom(item: SearchEntry): QueueEntry {
  const track = trackIdentity(item);
  return {
    key: queueKey(track),
    track,
    metadata: {
      title: item.title,
      artist: item.artist,
      album: item.album,
      durationSeconds: item.duration,
      cover: item.cover,
    },
  };
}

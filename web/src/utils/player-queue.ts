import type { QueueEntry, SearchEntry, TrackIdentity } from '../types/music';

const providers = new Set(['qq', 'netease', 'kuwo', 'migu']);
export const queueKey = (track: TrackIdentity) =>
  JSON.stringify([track.providerId, track.platformId]);
export function trackIdentity(item: SearchEntry): TrackIdentity {
  const providerId =
    'resolveState' in item
      ? item.source
      : (item.recordingIdentity?.providerId ?? item.providerId ?? item.source);
  // QQ、网易云、酷我的 Song.mid 可用作平台 ID；咪咕需要明确的 contentId。
  const platformId =
    'resolveState' in item
      ? item.platformId
      : (item.recordingIdentity?.platformId ??
        (['qq', 'netease', 'kuwo'].includes(providerId) ? item.mid : undefined));
  if (
    !providers.has(providerId) ||
    typeof platformId !== 'string' ||
    !platformId.trim() ||
    platformId.length > 128
  )
    throw new Error('此记录缺少可信歌曲身份，请重新搜索并选择具体版本');
  if (providerId === 'migu' && !/^[1-9][0-9]{0,31}$/.test(platformId))
    throw new Error('此咪咕记录缺少有效contentId，请重新搜索具体版本');
  return { providerId: providerId as TrackIdentity['providerId'], platformId };
}

export function queueEntryFrom(item: SearchEntry): QueueEntry {
  const track = trackIdentity(item);
  return {
    key: queueKey(track),
    track,
    metadata: {
      title: item.title || item.name,
      artist: item.artist,
      album: item.album,
      durationSeconds: 'resolveState' in item ? item.duration : null,
      cover: item.cover,
    },
  };
}

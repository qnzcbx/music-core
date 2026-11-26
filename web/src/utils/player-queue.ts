import type { QueueEntry, SearchEntry, Song, TrackIdentity } from '../types/music';

const aliases: Record<string, string> = {
  QQMusicClient: 'qq',
  NeteaseMusicClient: 'netease',
  KuwoMusicClient: 'kuwo',
  KugouMusicClient: 'kugou',
  SoundCloudMusicClient: 'soundcloud',
  MiguMusicClient: 'migu',
  FMAMusicClient: 'fma',
  AudiusMusicClient: 'audius',
};
const providers = new Set(['qq', 'netease', 'kuwo', 'migu']);
export const queueKey = (track: TrackIdentity) =>
  JSON.stringify([track.providerId, track.platformId]);
export function trackIdentity(item: SearchEntry): TrackIdentity {
  const provider =
    'resolveState' in item
      ? item.source
      : (item.recordingIdentity?.providerId ?? item.providerId ?? item.source);
  const providerId = aliases[provider] ?? provider;
  // 仅对这些旧版适配器而言，Song.mid 才是已知的平台 ID。
  // 例如，咪咕（Migu）必须使用原始的 Candidate 身份，而不能据此推断出 contentId。
  const platformId =
    'resolveState' in item
      ? item.platformId
      : (item.recordingIdentity?.platformId ??
        (['qq', 'netease', 'kuwo', 'kugou', 'soundcloud', 'audius', 'fma'].includes(providerId)
          ? item.mid
          : undefined));
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
export function requireQueueMedia(entry: QueueEntry, song: Song) {
  const identity = song.recordingIdentity;
  if (song.providerId !== entry.track.providerId || !identity || queueKey(identity) !== entry.key)
    throw new Error('解析资源与队列歌曲身份不匹配，没有切换播放器');
}

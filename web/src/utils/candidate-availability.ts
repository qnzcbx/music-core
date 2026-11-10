import type { SearchEntry, CandidateAvailability } from '../types/music.ts';

export function availabilityOf(song: SearchEntry, now = Date.now()): CandidateAvailability {
  if (!('resolveState' in song)) return 'unknown';
  if (song.resolveState === 'resolving') return 'resolving';
  if (song.resolveState === 'failed') return ['timeout', 'unsupported', 'stale'].includes(song.availability ?? '') ? song.availability! : 'failed';
  if (song.availability === 'ready') {
    return song.availabilityValidUntil && song.availabilityValidUntil > now ? 'ready' : 'stale';
  }
  return song.availability ?? 'unknown';
}

export const availabilityLabels: Record<CandidateAvailability, string> = {
  unknown: '资源未确认', queued: '等待解析', resolving: '正在解析', ready: '资源已就绪',
  failed: '本次解析失败', stale: '状态已过期',
  timeout: '本次解析超时', unsupported: '媒体明确不支持',
};

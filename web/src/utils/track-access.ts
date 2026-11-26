import type { SearchEntry } from '../types/music.ts';
export function downloadBlockReason(song: SearchEntry): string {
  const provider = ('providerId' in song && song.providerId) || song.source;
  const strict = ['fma', 'audius', 'FMAMusicClient', 'AudiusMusicClient'].includes(provider);
  const decision = song.trackAccess?.download;
  if (!decision && !strict) return '';
  if (decision?.evidence === 'desktop-source-policy' && decision.state === 'unknown') return '';
  return decision?.state === 'allowed' ? '' : decision?.reason || '下载权限尚未确认';
}
export function playbackBlockReason(song: SearchEntry): string {
  const decision = song.trackAccess?.playback;
  // 元数据未知时，仍可由用户显式解析；而一旦某个 gate（判定条件/门槛）已知，它就是最终结果。
  return decision?.state === 'denied' ? decision.reason : '';
}

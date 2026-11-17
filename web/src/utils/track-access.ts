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
  // Metadata unknown may still be explicitly resolved by the user; a known gate is final.
  return decision?.state === 'denied' ? decision.reason : '';
}

import type { SearchEntry } from '../types/music.ts';

export function downloadBlockReason(song: SearchEntry): string {
  return song.downloadAllowed === false ? '此来源暂不支持下载，或曲目明确禁止下载' : '';
}

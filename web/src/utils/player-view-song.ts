import type { Song, SearchEntry, QueueEntry } from '../types/music';
/** Held media takes precedence over metadata which may already have expired. No IO. */
export function playerViewSong(active: Song|null, queue: readonly QueueEntry[], candidates: readonly SearchEntry[], id?:string): SearchEntry|undefined {
  if(!id)return active??undefined;
  if(active&&(active.id===id||active.candidateId===id))return active;
  return queue.find(entry=>entry.key===id||entry.resolved?.id===id||entry.resolved?.candidateId===id)?.resolved??candidates.find(song=>song.id===id);
}
export const isPlayerPath=(path:string)=>path==='/player'||path.startsWith('/player/');

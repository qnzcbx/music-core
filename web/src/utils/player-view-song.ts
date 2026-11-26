import type { Song, SearchEntry, QueueEntry } from '../types/music';

/** 已持有的媒体优先于可能已过期的元数据。不进行 IO。 */
export function playerViewSong(
  active: Song | null,
  queue: readonly QueueEntry[],
  candidates: readonly SearchEntry[],
  id?: string,
): SearchEntry | undefined {
  if (!id) return active ?? undefined;
  if (active && (active.id === id || active.candidateId === id)) return active;
  return (
    queue.find(
      (entry) =>
        entry.key === id || entry.resolved?.id === id || entry.resolved?.candidateId === id,
    )?.resolved ?? candidates.find((song) => song.id === id)
  );
}
export const isPlayerPath = (path: string) => path === '/player' || path.startsWith('/player/');

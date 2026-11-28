import type { LocalSong } from '../types/music';

type LibraryMetadata = {
  title?: string | null;
  artist?: string | null;
  album?: string | null;
  cover?: string | null;
  durationSeconds?: number | null;
  path?: string;
};

export function matchesLibrarySearch(song: LibraryMetadata, query: string) {
  const search = query.trim().toLowerCase();
  return !search || [song.title, song.artist].some((value) => value?.toLowerCase().includes(search));
}

export function librarySong(fileId: string, song: LibraryMetadata): LocalSong {
  const filename = song.path?.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '');
  return {
    kind: 'local', fileId, id: JSON.stringify(['local', fileId]),
    title: song.title?.trim() || filename || '未命名歌曲', artist: song.artist || '', album: song.album || '',
    cover: song.cover || null, duration: song.durationSeconds ?? null,
  };
}

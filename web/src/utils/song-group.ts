import type { SearchEntry } from '../types/music.ts';

export interface SongGroup {
  key: string;
  title: string;
  artist: string;
  representative: SearchEntry;
  versions: SearchEntry[];
  expanded: boolean;
}

// 只统一空白与大小写，版本标签、标点和年份仍参与展示分组。
function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/[\s\u3000]+/gu, ' ');
}

export function createSongGroupState() {
  const states = new Map<string, { expanded: boolean; locked: boolean; representative?: string }>();

  function update(songs: readonly SearchEntry[], sources: readonly string[]): SongGroup[] {
    const groups = new Map<string, SearchEntry[]>();
    const rank = (song: SearchEntry) => {
      const index = sources.indexOf(song.identity.providerId);
      return index < 0 ? sources.length : index;
    };
    for (const song of songs) {
      const title = normalize(song.title);
      const artist = normalize(song.artist);
      const key = title && artist ? JSON.stringify([title, artist]) : JSON.stringify(['unknown', song.id]);
      const group = groups.get(key);
      if (group) group.push(song);
      else groups.set(key, [song]);
    }
    for (const key of states.keys()) if (!groups.has(key)) states.delete(key);
    return Array.from(groups, ([key, versions]) => {
      const state = states.get(key) ?? { expanded: false, locked: false };
      states.set(key, state);
      versions.sort((a, b) => rank(a) - rank(b));
      const current = state.locked ? versions.find((song) => song.id === state.representative) : undefined;
      const representative = current ?? versions[0]!;
      state.representative = representative.id;
      return { key, versions, representative, title: representative.title, artist: representative.artist, expanded: state.expanded };
    });
  }

  return {
    update,
    reset: () => states.clear(),
    lockRepresentatives() {
      for (const state of states.values()) state.locked = true;
    },
    toggle(key: string) {
      const state = states.get(key);
      if (state) {
        state.expanded = !state.expanded;
        state.locked = true;
      }
    },
  };
}

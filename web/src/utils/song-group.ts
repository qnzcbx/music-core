import type { SearchEntry as Song } from '../types/music.ts';
import { availabilityOf } from './candidate-availability.ts';
import { sourcePreferenceOrder } from '../config/source-profile.ts';

export interface SongGroup {
  key: string;
  title: string;
  artist: string;
  representative: Song;
  versions: Song[];
  expanded: boolean;
  protected?: boolean;
  autoStable?: boolean;
}
export function sourceOrder(sources: readonly string[]): string[] {
  return sourcePreferenceOrder(sources);
}

// 只统一空白与大小写，不删除版本标签、标点或年份。
export function normalizeTitle(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s\u3000]+/gu, ' ');
}
export const normalizeArtist = normalizeTitle;

export function buildSongGroups(
  songs: readonly Song[],
  sources: readonly string[],
  now = Date.now(),
): SongGroup[] {
  sources = sourceOrder(sources);
  const groups = new Map<string, SongGroup>();
  const rank = (song: Song) => {
    const index = sources.indexOf(
      ('providerId' in song && song.providerId) || song.source,
    );
    return index < 0 ? sources.length : index;
  };
  for (const song of songs) {
    const title = song.title ?? song.name;
    // 缺少标题或歌手时不猜测同曲关系。JSON 元组避免字符串拼接冲突。
    const key = song.recordingIdentity
      ? JSON.stringify([
          'recording',
          song.recordingIdentity.providerId,
          song.recordingIdentity.platformId,
        ])
      : normalizeTitle(title) && normalizeArtist(song.artist)
        ? JSON.stringify([normalizeTitle(title), normalizeArtist(song.artist)])
        : JSON.stringify(['unknown', song.source, song.id]);
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        title,
        artist: song.artist,
        representative: song,
        versions: [],
        expanded: false,
      };
      groups.set(key, group);
    }
    group.versions.push(song);
  }
  for (const group of groups.values()) {
    // 真实检查仍有效的 ready 优先，再按注册表传入的顺序；不按勾选先后估计成功率。
    group.versions.sort(
      (a, b) =>
        Number(availabilityOf(b, now) === 'ready') - Number(availabilityOf(a, now) === 'ready') ||
        rank(a) - rank(b),
    );
    group.representative = group.versions[0]!;
    group.title = group.representative.title ?? group.representative.name;
    group.artist = group.representative.artist;
  }
  return [...groups.values()];
}

export function createSongGroupState() {
  type State = {
    expanded: boolean;
    locked: boolean;
    selected?: string;
    representative?: string;
    score?: number;
    promoted?: boolean;
  };
  const states = new Map<string, State>();
  function update(
    songs: readonly Song[],
    order: readonly string[],
    activeId?: string,
    now = Date.now(),
    playing?: Song,
  ) {
    order = sourceOrder(order);
    const groups = buildSongGroups(songs, order, now);
    const keys = new Set(groups.map((group) => group.key));
    for (const key of states.keys()) if (!keys.has(key)) states.delete(key);
    for (const group of groups) {
      const state = states.get(group.key) ?? { expanded: false, locked: false };
      states.set(group.key, state);
      const score = (song: Song) => {
        const source = ('providerId' in song && song.providerId) || song.source;
        const rank = order.indexOf(source);
        return (
          (availabilityOf(song, now) === 'ready' ? 0 : 1) * (order.length + 1) +
          (rank < 0 ? order.length : rank)
        );
      };
      const current = group.versions.find((song) => song.id === state.representative);
      const selected = group.versions.find((song) => song.id === state.selected);
      const active = group.versions.find(
        (song) =>
          (activeId &&
            (song.id === activeId || ('resolveState' in song && song.resolvedId === activeId))) ||
          (playing?.mid &&
            song.mid === playing.mid &&
            (('providerId' in song && song.providerId) || song.source) ===
              (('providerId' in playing && playing.providerId) || playing.source)),
      );
      let chosen = selected ?? active ?? (state.locked ? current : undefined);
      if (!chosen) {
        const best = group.versions[0]!;
        // 只允许未交互的组向更好的历史分数移动；过期不会触发来回切换。
        chosen =
          !current || state.score === undefined || score(best) < state.score ? best : current;
      }
      state.representative = chosen.id;
      state.score = Math.min(state.score ?? score(chosen), score(chosen));
      group.representative = chosen;
      group.title = chosen.title ?? chosen.name;
      group.artist = chosen.artist;
      group.expanded = state.expanded;
      group.protected = !!(selected || active);
      group.autoStable = !!state.promoted;
    }
    return groups;
  }
  return {
    update,
    reset: () => states.clear(),
    lockRepresentatives() {
      for (const state of states.values()) state.locked = true;
    },
    promote(song: Song, groups: readonly SongGroup[], now = Date.now()) {
      const group = groups.find((group) =>
        group.versions.some((version) => version.id === song.id),
      );
      if (!group || group.protected || group.autoStable || availabilityOf(song, now) !== 'ready')
        return false;
      const state = states.get(group.key);
      if (!state || state.selected) return false;
      state.representative = song.id;
      state.locked = true;
      state.promoted = true;
      return true;
    },
    toggle(key: string) {
      const state = states.get(key);
      if (state) {
        state.expanded = !state.expanded;
        state.locked = true;
      }
    },
    select(song: Song, groups: readonly SongGroup[]) {
      const group = groups.find((group) =>
        group.versions.some(
          (version) =>
            version.id === song.id ||
            ('candidateId' in song && song.candidateId === version.id) ||
            ('resolveState' in version && version.resolvedId === song.id),
        ),
      );
      if (!group) return;
      const version = group.versions.find(
        (version) =>
          version.id === song.id ||
          ('candidateId' in song && song.candidateId === version.id) ||
          ('resolveState' in version && version.resolvedId === song.id),
      )!;
      const state = states.get(group.key)!;
      state.selected = version.id;
      state.locked = true;
    },
  };
}

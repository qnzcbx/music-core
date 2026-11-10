import { computed, readonly, ref } from 'vue';

export const PLAYER_LAYOUTS = [
  { id: 'classic', name: '经典唱片机', description: '唱片机在左，同步歌词在右' },
  { id: 'vinyl-wide', name: '沉浸大唱片', description: '歌词在左，大唱片延伸至画面之外' },
  { id: 'square-cover', name: '方形封面', description: '完整专辑封面，与歌词并排' },
  { id: 'lyrics-only', name: '纯净歌词', description: '留白之间，专注每一句歌词' },
] as const;
export type PlayerLayout = typeof PLAYER_LAYOUTS[number]['id'];
export type LyricAlignment = 'left' | 'center';
export const DEFAULT_LYRIC_ALIGNMENTS: Record<PlayerLayout, LyricAlignment> = {
  classic: 'center', 'vinyl-wide': 'left', 'square-cover': 'center', 'lyrics-only': 'center',
};
export const PLAYER_LAYOUT_KEY = 'media-lab.player-layout.v1';
type LayoutStorage = Pick<Storage, 'getItem' | 'setItem'>;
export function isPlayerLayout(value: unknown): value is PlayerLayout {
  return PLAYER_LAYOUTS.some(item => item.id === value);
}
export function isLyricAlignment(value: unknown): value is LyricAlignment { return value === 'left' || value === 'center'; }
/** Synchronous, versioned visual preference; never stores player/media data. */
export function createPlayerLayoutSelection(beforeChange: () => void = () => {}, storage?: LayoutStorage) {
  let initial: PlayerLayout = 'classic';
  const alignments = { ...DEFAULT_LYRIC_ALIGNMENTS };
  try {
    const saved = JSON.parse(storage?.getItem(PLAYER_LAYOUT_KEY) ?? 'null');
    if (saved?.version === 1 && (saved.layout === 'classic' || saved.layout === 'vinyl-wide')) initial = saved.layout;
    if (saved?.version === 2) {
      if (isPlayerLayout(saved.layout)) initial = saved.layout;
      for (const { id } of PLAYER_LAYOUTS) {
        const value = saved.lyricAlignments?.[id];
        if (isLyricAlignment(value)) alignments[id] = value;
      }
    }
  } catch { /* Missing, corrupt or denied storage keeps the default. */ }
  const layout = ref<PlayerLayout>(initial);
  const lyricAlignments = ref(alignments);
  const lyricAlignment = computed(() => lyricAlignments.value[layout.value]);
  function persist() {
    try { storage?.setItem(PLAYER_LAYOUT_KEY, JSON.stringify({ version: 2, layout: layout.value, lyricAlignments: lyricAlignments.value })); }
    catch { /* The current root still keeps the user's choices in memory. */ }
  }
  function selectLayout(value: unknown) {
    if (!isPlayerLayout(value) || value === layout.value) return false;
    beforeChange();
    layout.value = value;
    persist();
    return true;
  }
  function selectLyricAlignment(value: unknown) {
    if (!isLyricAlignment(value) || value === lyricAlignment.value) return false;
    lyricAlignments.value = { ...lyricAlignments.value, [layout.value]: value };
    persist();
    return true;
  }
  return { layout: readonly(layout), selectLayout, lyricAlignments: readonly(lyricAlignments), lyricAlignment, selectLyricAlignment };
}
export function startPlayerLayoutSelection() {
  let storage: LayoutStorage | undefined;
  try { storage = window.localStorage; } catch { /* Even accessing the property can throw. */ }
  return createPlayerLayoutSelection(undefined, storage);
}

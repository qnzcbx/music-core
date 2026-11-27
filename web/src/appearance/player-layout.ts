import { computed, readonly, ref } from 'vue';

export const PLAYER_LAYOUTS = [
  { id: 'classic', name: '经典唱片机', description: '唱片机在左，同步歌词在右' },
  { id: 'vinyl-wide', name: '沉浸大唱片', description: '歌词在左，大唱片延伸至画面之外' },
  { id: 'square-cover', name: '方形封面', description: '完整专辑封面，与歌词并排' },
  { id: 'lyrics-only', name: '纯净歌词', description: '留白之间，专注每一句歌词' },
] as const;
export type PlayerLayout = (typeof PLAYER_LAYOUTS)[number]['id'];
export type PlayerBackground = 'cover' | 'light' | 'dark';
export const PLAYER_RING_PRESETS = [
  { id: 'smoky', name: '烟灰', colors: '#aeb0b5,#6f7178' },
  { id: 'frost', name: '雾银', colors: '#d8e0e8,#949ea8' },
  { id: 'amber', name: '琥珀', colors: '#b59672,#5e4630' },
  { id: 'obsidian', name: '曜石', colors: '#43464b,#16181b' },
  { id: 'glacier', name: '冰川蓝', colors: '#b6dce9,#638da8' },
  { id: 'turquoise', name: '松石绿', colors: '#9acfc0,#3d8e7d' },
  { id: 'violet', name: '烟紫', colors: '#c2b4d2,#89749d' },
  { id: 'lemon', name: '柠黄', colors: '#ece3a3,#b8a646' },
  { id: 'rose', name: '玫瑰红', colors: '#e1a8bb,#a85b77' },
] as const;
export type RingPreset = (typeof PLAYER_RING_PRESETS)[number]['id'];
function isRingPreset(value: unknown): value is RingPreset {
  return PLAYER_RING_PRESETS.some((item) => item.id === value);
}
export type LyricAlignment = 'left' | 'center';
export const DEFAULT_LYRIC_ALIGNMENTS: Record<PlayerLayout, LyricAlignment> = {
  classic: 'center',
  'vinyl-wide': 'left',
  'square-cover': 'center',
  'lyrics-only': 'center',
};
export const PLAYER_LAYOUT_KEY = 'music-core.player-layout.v1';
type LayoutStorage = Pick<Storage, 'getItem' | 'setItem'>;
export function isPlayerLayout(value: unknown): value is PlayerLayout {
  return PLAYER_LAYOUTS.some((item) => item.id === value);
}
export function isLyricAlignment(value: unknown): value is LyricAlignment {
  return value === 'left' || value === 'center';
}
/** 同步、带版本号的视觉偏好，绝不存储播放器/媒体数据。 */
export function createPlayerLayoutSelection(
  beforeChange: () => void = () => {},
  storage?: LayoutStorage,
) {
  let initial: PlayerLayout = 'classic';
  const alignments = { ...DEFAULT_LYRIC_ALIGNMENTS };
  const backgrounds = Object.fromEntries(
    PLAYER_LAYOUTS.map((item) => [item.id, 'cover']),
  ) as Record<PlayerLayout, PlayerBackground>;
  let savedRing: RingPreset = 'smoky';
  try {
    const saved = JSON.parse(storage?.getItem(PLAYER_LAYOUT_KEY) ?? 'null');
    if (saved?.version === 3) {
      if (isPlayerLayout(saved.layout)) initial = saved.layout;
      for (const { id } of PLAYER_LAYOUTS) {
        const value = saved.lyricAlignments?.[id];
        if (isLyricAlignment(value)) alignments[id] = value;
        const background = saved.backgrounds?.[id];
        if (['cover', 'light', 'dark'].includes(background)) backgrounds[id] = background;
      }
      if (isRingPreset(saved.ringPreset)) savedRing = saved.ringPreset;
    }
  } catch {
    /* 存储缺失、损坏或被拒绝时保持默认值。 */
  }
  const layout = ref<PlayerLayout>(initial);
  const lyricAlignments = ref(alignments);
  const backgroundModes = ref(backgrounds);
  const backgroundMode = computed(() => backgroundModes.value[layout.value]);
  const ringPreset = ref<RingPreset>(savedRing);
  const lyricAlignment = computed(() => lyricAlignments.value[layout.value]);
  function persist() {
    try {
      storage?.setItem(
        PLAYER_LAYOUT_KEY,
        JSON.stringify({
          version: 3,
          layout: layout.value,
          lyricAlignments: lyricAlignments.value,
          backgrounds: backgroundModes.value,
          ringPreset: ringPreset.value,
        }),
      );
    } catch {
      /* 当前根节点仍在内存中保留用户的选择。 */
    }
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
  function selectBackground(value: PlayerBackground) {
    if (!['cover', 'light', 'dark'].includes(value)) return;
    backgroundModes.value = { ...backgroundModes.value, [layout.value]: value };
    persist();
  }
  function selectRingPreset(value: RingPreset) {
    if (!isRingPreset(value)) return;
    ringPreset.value = value;
    persist();
  }
  return {
    backgroundMode,
    selectBackground,
    ringPreset: readonly(ringPreset),
    selectRingPreset,
    layout: readonly(layout),
    selectLayout,
    lyricAlignments: readonly(lyricAlignments),
    lyricAlignment,
    selectLyricAlignment,
  };
}
export function startPlayerLayoutSelection() {
  let storage: LayoutStorage | undefined;
  try {
    storage = window.localStorage;
  } catch {
    /* 即便只是访问该属性也可能抛异常。 */
  }
  return createPlayerLayoutSelection(undefined, storage);
}

import { onUnmounted, readonly, shallowRef, watch, type Ref } from "vue";
import {
  createPaletteSelection,
  defaultAmbientPalette,
  loadCoverPalette,
} from "../utils/ambient-palette";
export function useCoverPalette(cover: Readonly<Ref<string | null | undefined>>) {
  const palette = shallowRef(defaultAmbientPalette);
  const selection = createPaletteSelection(loadCoverPalette, (value) => {
    palette.value = value;
  });
  // 新封面尚未取色完成时保留上一层，避免闪烁。
  watch(
    cover,
    (url) => {
      void selection.select(url);
    },
    { immediate: true },
  );
  onUnmounted(selection.dispose);
  return readonly(palette);
}

<script setup lang="ts">
import { nextTick, onUnmounted, shallowRef, ref, watch, computed } from "vue";
import type { AmbientPalette } from "../utils/ambient-palette";
import { useReducedMotion } from "../composables/useReducedMotion";
const props = withDefaults(
  defineProps<{
    palette: AmbientPalette;
    intensity?: number;
    blur?: number;
    variant?: "player" | "page";
  }>(),
  { intensity: 1, blur: 42, variant: "player" },
);
const reduced = useReducedMotion();
const layers = shallowRef([props.palette, props.palette]);
const active = ref(0),
  fading = ref(false);
let pending: AmbientPalette | undefined,
  timer: ReturnType<typeof setTimeout> | undefined,
  frame = 0,
  generation = 0;
const config = computed(() => ({
  "--ambient-intensity": Math.max(0, Math.min(1, props.intensity)),
  "--ambient-blur": `${Math.max(0, Math.min(90, props.blur))}px`,
}));
const style = (palette: AmbientPalette) => ({
  "--ambient-base-left": palette.baseLeft,
  "--ambient-base-right": palette.baseRight,
  "--ambient-left": palette.left,
  "--ambient-center": palette.center,
  "--ambient-right": palette.right,
});
async function apply(palette: AmbientPalette) {
  if (palette.key === layers.value[active.value]!.key) {
    pending = undefined;
    return;
  }
  if (fading.value && !reduced.value) {
    pending = palette;
    return;
  }
  const token = ++generation;
  clearTimeout(timer);
  cancelAnimationFrame(frame);
  pending = undefined;
  if (reduced.value) {
    layers.value = [palette, palette];
    active.value = 0;
    fading.value = false;
    return;
  }
  const next = 1 - active.value;
  const updated = [...layers.value];
  updated[next] = palette;
  layers.value = updated;
  await nextTick();
  if (token !== generation) return;
  // 先绘制备用层，再开始只改变透明度的过渡。
  frame = requestAnimationFrame(() => {
    if (token !== generation) return;
    fading.value = true;
    active.value = next;
    timer = setTimeout(finish, 980);
  });
}
function finish() {
  if (!fading.value) return;
  clearTimeout(timer);
  fading.value = false;
  const next = pending;
  pending = undefined;
  if (next) void apply(next);
}
watch(
  () => props.palette,
  (palette) => {
    void apply(palette);
  },
);
watch(reduced, () => {
  generation++;
  clearTimeout(timer);
  cancelAnimationFrame(frame);
  fading.value = false;
  pending = undefined;
  layers.value = [props.palette, props.palette];
  active.value = 0;
});
onUnmounted(() => {
  generation++;
  clearTimeout(timer);
  cancelAnimationFrame(frame);
  pending = undefined;
});
</script>
<template>
  <div
    class="ambient-background"
    :class="`ambient-${variant}`"
    :style="config"
    aria-hidden="true"
    :data-palette-key="layers[active]?.key"
    :data-palette-evidence="layers[active]?.evidence"
  >
    <div
      v-for="(palette, index) in layers"
      :key="index"
      class="ambient-layer"
      :class="{ 'ambient-active': index === active }"
      :style="style(palette)"
      @transitionend="
        (event) => {
          if (event.propertyName === 'opacity' && index === active) finish();
        }
      "
    />
  </div>
</template>
<style scoped>
.ambient-background {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  background: #f3f2e9;
  isolation: isolate;
}
.ambient-player {
  position: fixed;
}
.ambient-layer {
  position: absolute;
  inset: -12%;
  opacity: 0;
  filter: blur(var(--ambient-blur));
  transition: opacity 900ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: opacity;
  background:
    radial-gradient(ellipse 60% 84% at 12% 82%, var(--ambient-left) 0%, transparent 78%),
    radial-gradient(ellipse 66% 78% at 91% 18%, var(--ambient-right) 0%, transparent 76%),
    radial-gradient(ellipse 45% 60% at 49% 43%, var(--ambient-center) 0%, transparent 82%),
    linear-gradient(122deg, var(--ambient-base-left), var(--ambient-base-right));
}
.ambient-background::after {
  content: "";
  position: absolute;
  inset: 0;
  opacity: 0.17;
  background: radial-gradient(
    ellipse 80% 50% at 43% 8%,
    rgba(255, 255, 255, 0.63),
    transparent 92%
  );
}
.ambient-active {
  opacity: var(--ambient-intensity);
}
.ambient-page .ambient-layer {
  background-position: center;
}
@media (prefers-reduced-motion: reduce) {
  .ambient-layer {
    transition: none;
    will-change: auto;
  }
}
</style>

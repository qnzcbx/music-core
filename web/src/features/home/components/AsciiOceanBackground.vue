<script setup lang="ts">
import { ref, watch, onUnmounted } from "vue";
import { useReducedMotion } from "../../../composables/useReducedMotion";
import { HomeOceanEngine } from "../ascii-ocean/engine";
import { HOME_SHARKS } from "../ascii-ocean/config";
const canvas = ref<HTMLCanvasElement>(),
  failed = ref(false),
  reduced = useReducedMotion();
const experiment = import.meta.env.DEV ? new URLSearchParams(location.search).get("ocean") : null;
let engine: HomeOceanEngine | undefined;
watch(
  canvas,
  (element) => {
    engine?.destroy();
    engine = undefined;
    if (!element) return;
    try {
      engine = new HomeOceanEngine(
        element,
        experiment === "three"
          ? [HOME_SHARKS[0]!, HOME_SHARKS[2]!, HOME_SHARKS[4]!]
          : experiment === "two"
            ? [HOME_SHARKS[0]!, HOME_SHARKS[2]!]
            : HOME_SHARKS,
      );
      if (import.meta.env.DEV) Object.assign(element, { __ocean: engine });
    } catch {
      failed.value = true;
    }
  },
  { flush: "post" },
);
onUnmounted(() => engine?.destroy());
</script>
<template>
  <div
    class="ascii-ocean-background"
    aria-hidden="true"
    :data-ocean-motion="
      reduced
        ? 'reduced'
        : experiment === 'off'
          ? 'experiment-off'
          : failed
            ? 'unavailable'
            : 'animated'
    "
  >
    <canvas v-if="!reduced && !failed && experiment !== 'off'" ref="canvas" />
  </div>
</template>
<style scoped>
.ascii-ocean-background {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  color: var(--app-ocean-ink);
}
canvas {
  display: block;
  width: 100%;
  height: 100%;
  font-family: Consolas, "Segoe UI Symbol", "Courier New", monospace;
}
</style>

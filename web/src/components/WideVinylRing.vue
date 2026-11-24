<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import {
  WIDE_COVER_RATIO,
  buildRingField,
  paintRing,
  type RingField,
  type RingPreset,
} from './wide-vinyl/ring-field';

const props = withDefaults(defineProps<{ preset?: RingPreset }>(), { preset: 'smoky' });
const emit = defineEmits<{ ready: [] }>();
const canvas = ref<HTMLCanvasElement>();
let observer: ResizeObserver | undefined;
let field: RingField | undefined;
let frame = 0;
let painted: RingPreset | undefined;

function draw() {
  frame = 0;
  const node = canvas.value;
  if (!node || !node.clientWidth) return;
  const context = node.getContext('2d');
  if (!context) return;
  const size = Math.min(
    1536,
    Math.max(256, Math.ceil((node.clientWidth * Math.min(devicePixelRatio || 1, 1.5)) / 64) * 64),
  );
  if (field?.size === size && painted === props.preset) return;
  if (!field || field.size !== size) {
    node.width = node.height = size;
    field = buildRingField(size, WIDE_COVER_RATIO);
  }
  paintRing(context, field, props.preset);
  painted = props.preset;
  emit('ready');
}
function schedule() {
  if (!frame) frame = requestAnimationFrame(draw);
}
watch(() => props.preset, schedule);
onMounted(() => {
  observer = new ResizeObserver(schedule);
  if (canvas.value) observer.observe(canvas.value);
  schedule();
});
onBeforeUnmount(() => {
  observer?.disconnect();
  cancelAnimationFrame(frame);
  field = undefined;
});
</script>

<template>
  <canvas
    ref="canvas"
    class="wide-ring-canvas"
    aria-hidden="true"
    :data-ring-preset="preset"
  />
</template>

<style scoped>
.wide-ring-canvas {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  pointer-events: none;
}
</style>

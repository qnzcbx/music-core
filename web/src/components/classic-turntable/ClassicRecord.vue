<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { extractWithDiagnostic, type RGB } from '../../utils/ambient-palette';
import { coverSamples, paintRecord, neutralMaterial } from './record-material';

const props = defineProps<{ cover?: string | null }>();
const emit = defineEmits<{ ready: [] }>();
const canvas = ref<HTMLCanvasElement>();
const evidence = ref('neutral');
let colors: RGB[] = [];
let revision = 0,
  paintedRevision = -1,
  size = 0,
  frame = 0;
let observer: ResizeObserver | undefined;

function draw() {
  frame = 0;
  const node = canvas.value;
  if (!node?.clientWidth) return;
  const nextSize = Math.min(
    1024,
    Math.max(192, Math.ceil((node.clientWidth * Math.min(devicePixelRatio, 1.5)) / 64) * 64),
  );
  if (size === nextSize && paintedRevision === revision) return;
  const context = node.getContext('2d');
  if (!context) return;
  node.width = node.height = size = nextSize;
  paintRecord(context, size, neutralMaterial, { opacity: 0.97, blur: 8 }, colors);
  paintedRevision = revision;
  node.dataset.paints = String(Number(node.dataset.paints || 0) + 1);
  emit('ready');
}
function schedule() {
  if (!frame) frame = requestAnimationFrame(draw);
}
watch(
  () => props.cover,
  async (url) => {
    const current = ++revision;
    colors = Array.from({ length: 16 }, () => [...neutralMaterial.neutral] as unknown as RGB);
    evidence.value = url ? 'loading' : 'neutral';
    schedule();
    if (!url) return;
    try {
      const result = await extractWithDiagnostic(url, (image) =>
        coverSamples(image, neutralMaterial),
      );
      if (current !== revision) return;
      colors = result.colors;
      evidence.value = result.diagnostic.via;
    } catch {
      if (current !== revision) return;
      evidence.value = 'neutral';
    }
    // 同一封面的最终采样也是一次有效材质变更。
    paintedRevision = -1;
    schedule();
  },
  { immediate: true, flush: "sync" },
);
onMounted(() => {
  observer = new ResizeObserver(schedule);
  if (canvas.value) observer.observe(canvas.value);
  schedule();
});
onBeforeUnmount(() => {
  revision++;
  observer?.disconnect();
  cancelAnimationFrame(frame);
});
</script>
<template>
  <canvas
    ref="canvas"
    class="classic-record"
    :data-sampling="evidence"
    aria-hidden="true"
  />
</template>
<style scoped>
.classic-record {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  pointer-events: none;
}
</style>

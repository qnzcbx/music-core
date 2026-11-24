<script setup lang="ts">
import { defineAsyncComponent, inject, onUnmounted, ref } from 'vue';
import 'ink-breath/vue.css';
import { APPEARANCE, type Appearance } from '../../../appearance/theme';
import { useReducedMotion } from '../../../composables/useReducedMotion';

defineProps<{ text: string }>();
const appearance = inject<Appearance>(APPEARANCE)!;
const theme = ref(appearance.effective);
const reduced = useReducedMotion();
const failed = ref(false);
// 场景资源加载失败时保留首页搜索；水墨模块只在首页需要时加载。
const InkScene = defineAsyncComponent({
  loader: () => import('ink-breath/vue').then((module) => module.InkScene),
  onError(_error, _retry, fail) {
    failed.value = true;
    fail();
  },
});
onUnmounted(
  appearance.subscribe(() => {
    theme.value = appearance.effective;
  }),
);
</script>

<template>
  <div
    class="home-ink-background"
    aria-hidden="true"
    :data-ink-state="failed ? 'unavailable' : reduced ? 'reduced' : 'animated'"
  >
    <InkScene
      v-if="!failed"
      motif="lotus-fish"
      text-layout="top"
      :text="text"
      :theme="theme"
      :renderer="reduced ? 'canvas' : 'auto'"
      quality="medium"
      :interactive="true"
      :auto-ink="!reduced"
      :active="!reduced"
      @error="failed = true"
    />
  </div>
</template>

<style scoped>
.home-ink-background {
  position: absolute;
  /* 首页视图会裁剪场景，侧边栏的动效不得改变 WebGL 缓冲区尺寸。 */
  inset-block: 0;
  left: 50%;
  width: 100vw;
  transform: translateX(-50%);
  overflow: hidden;
  background: var(--app-bg);
}
</style>

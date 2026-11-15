<script setup lang="ts">
import { defineAsyncComponent, onBeforeUnmount, ref, shallowRef, watch } from 'vue';
import HomeInkBackground from '../features/home/components/HomeInkBackground.vue';
import HomeGreeting from '../features/home/components/HomeGreeting.vue';
import HomeSearch from '../features/home/components/HomeSearch.vue';
import { useHomeBackground } from '../features/home/background';
const { background } = useHomeBackground();
const HomeVoiceBetween = defineAsyncComponent(
  () => import('../features/home/components/HomeVoiceBetween.vue'),
);
const piano = ref<{
  bindInputElement(element: HTMLInputElement | HTMLTextAreaElement): () => void;
}>();
const searchElement = shallowRef<HTMLInputElement | null>(null);
let unbind: (() => void) | undefined;
// 异步琴体与搜索框任意一方晚到都重新绑定；切走或替换元素先释放旧绑定。
watch(
  [background, piano, searchElement],
  ([mode, instrument, element]) => {
    unbind?.();
    unbind =
      mode === 'voice' && instrument && element ? instrument.bindInputElement(element) : undefined;
  },
  { flush: 'post' },
);
onBeforeUnmount(() => unbind?.());
const inkText = ref('');
</script>
<template>
  <section
    class="home-view"
    :class="{ 'has-voice': background === 'voice' }"
    aria-label="首页"
  >
    <HomeInkBackground
      v-if="background === 'ink'"
      :text="inkText"
    />
    <div class="home-main">
      <HomeGreeting /><HomeSearch
        @draft-change="inkText = $event"
        @input-ready="searchElement = $event"
      />
    </div>
    <div
      v-if="background === 'voice'"
      class="home-instrument"
      aria-label="字里弦间"
    >
      <HomeVoiceBetween ref="piano" />
    </div>
  </section>
</template>
<style scoped>
.home-view {
  position: relative;
  height: 100%;
  min-height: 0;
  width: 100%;
  display: grid;
  place-items: center;
  overflow: hidden;
  isolation: isolate;
  background: var(--app-bg);
}
.home-main {
  pointer-events: none;
  position: relative;
  z-index: 1;
  width: min(600px, calc(100% - 64px));
  text-align: center;
  transform: translateY(-24px);
}
.home-main :deep(.home-search) {
  pointer-events: auto;
}
@media (max-width: 600px) {
  .home-main {
    width: calc(100% - 36px);
    transform: translateY(-12px);
  }
  .home-main::before {
    inset: -40px -25px;
  }
}
@media (max-height: 440px) {
  .home-main {
    transform: none;
  }
  .home-main :deep(.home-greeting) {
    margin-bottom: 16px;
    font-size: 26px;
  }
  .home-main :deep(.search-hero) {
    height: 50px;
  }
}
</style>

<style scoped>
.home-view.has-voice {
  display: flex;
  flex-direction: column;
  justify-content: safe center;
  overflow: auto;
  padding: 32px 0 0 0;
}
.has-voice .home-main {
  flex-shrink: 0;
  transform: none;
}
.home-instrument {
  flex-shrink: 0;
  width: min(1080px, calc(100% - 48px));
  margin-top: 30px;
}
@media (max-width: 600px) {
  .home-view.has-voice {
    padding: 24px 0 0 0;
  }
  .home-instrument {
    width: calc(100% - 24px);
    margin-top: 20px;
  }
}
</style>

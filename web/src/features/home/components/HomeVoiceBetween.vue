<script setup lang="ts">
import { inject, onUnmounted, ref } from 'vue';
import { VoiceBetween, type VoiceBetweenHandle } from 'voice-between';
import { APPEARANCE, type Appearance } from '../../../appearance/theme';

const appearance = inject<Appearance>(APPEARANCE)!;
const theme = ref(appearance.effective);
const piano = ref<VoiceBetweenHandle>();
onUnmounted(
  appearance.subscribe(() => {
    theme.value = appearance.effective;
  }),
);

defineExpose({
  bindInputElement: (element: HTMLInputElement | HTMLTextAreaElement) =>
    piano.value?.bindInputElement(element) ?? (() => {}),
});
</script>
<template>
  <VoiceBetween
    ref="piano"
    :theme="theme"
    :show-controls="false"
    transparent
  />
</template>

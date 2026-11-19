<script setup lang="ts">
import ClassicMachine from "./classic-turntable/ClassicMachine.vue";
import ClassicRecord from "./classic-turntable/ClassicRecord.vue";
import CoverArt from "./CoverArt.vue";
import WideVinylRing from "./WideVinylRing.vue";
import { WIDE_COVER_RATIO, type RingPreset } from "./wide-vinyl/ring-field";
import type { AmbientPalette } from "../utils/ambient-palette";
import type { PlayerLayout } from "../appearance/player-layout";
import { ref, watch, nextTick } from "vue";


const props = defineProps<{
  cover?: string | null;
  coverKey: string;
  displayedCover?: string | null;
  playing: boolean;
  palette: AmbientPalette;
  label: string;
  layout?: PlayerLayout;
  ringPreset?: RingPreset;
  dark?: boolean;
}>();
const scene = ref<HTMLElement>();
function syncRing() {
  const cover = scene.value?.querySelector('.record-art-rotor')?.getAnimations()[0];
  const ring = scene.value?.querySelector(props.layout === 'classic' ? '.classic-record-rotor' : '.wide-ring-rotor')?.getAnimations()[0];
  if (cover && ring) ring.currentTime = cover.currentTime;
}
watch(() => [props.layout, props.playing], () => { void nextTick(syncRing); });
const emit = defineEmits<{ coverElement: [element: unknown]; displayed: [key: string, url: string | null] }>();
</script>
<template>
  <div
    ref="scene"
    class="vinyl-scene"
    :class="{ 'vinyl-playing': playing, 'vinyl-wide-scene': layout === 'vinyl-wide' }"
    :style="{ '--vinyl-tint': palette.left, '--wide-cover-ratio': WIDE_COVER_RATIO, '--spin-state': playing ? 'running' : 'paused' }"
  >
    <div class="turntable" role="img" :aria-label="`${label} · ${playing ? '播放中' : '已暂停'}`">
      <ClassicMachine v-if="layout === 'classic'" :playing="playing" :dark="!!dark" />
      <div v-if="layout === 'classic'" class="classic-disc"><div class="classic-record-rotor"><ClassicRecord :cover="displayedCover" @ready="syncRing" /></div><div class="classic-gloss" /></div>
      <div class="platter-shadow" />
      <div class="vinyl-grooves"><span class="vinyl-reflection" /></div>
      <template v-if="layout === 'vinyl-wide'">
        <div class="wide-ring-shadow" />
        <div class="wide-ring-rotor"><WideVinylRing :preset="ringPreset" @ready="syncRing" /></div>
        <div class="wide-ring-optics" />
      </template>
      <div
        :ref="(value) => emit('coverElement', value)"
        class="record-label"
        data-cover-role="large"
      >
        <div class="record-art-rotor">
          <Teleport to="#player-square-cover" defer :disabled="layout !== 'square-cover'">
            <CoverArt :key="coverKey" @displayed="emit('displayed', coverKey, $event)" clover-fallback data-player-cover :src="cover" :alt="`${label}封面`" />
          </Teleport>
        </div>
        <i class="spindle" aria-hidden="true" />
      </div>
      <div class="turntable-light" aria-hidden="true" />
    </div>

  </div>
</template>
<style scoped>
.vinyl-scene {
  width: min(100%, 448px);
  margin: auto;
  padding: 30px 14px 0;
}
.turntable {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 36px;
  background: #ffffff;
  box-shadow:
    16px 26px 42px #34473013,
    inset 0 0 0 1px #ffffffa8;
}
.platter-shadow {
  position: absolute;
  width: 84%;
  height: 84%;
  left: 5%;
  top: 9%;
  border-radius: 50%;
  background: #cdd4d8;
  box-shadow:
    inset 0 2px 6px #14281316,
    0 5px 8px #3b514128;
}
.vinyl-grooves {
  position: absolute;
  width: 78%;
  height: 78%;
  left: 8%;
  top: 12%;
  border-radius: 50%;
  overflow: hidden;
  background:
    repeating-radial-gradient(
      circle at center,
      rgba(255, 255, 255, 0.055) 0 1px,
      rgba(15, 25, 29, 0.065) 1px 3px
    ),
    radial-gradient(
      circle at 36% 28%,
      color-mix(
        in srgb,
        var(--vinyl-tint) 20%,
        #89999d
      ) 0%,
      #626d71 43%,
      #424b50 77%,
      #293237 100%
    );
  box-shadow:
    inset 0 0 0 4px #e5e9e33b,
    0 3px 8px #354b3342;
}
.vinyl-reflection {
  position: absolute;
  inset: 0;
  background: conic-gradient(
    from 35deg,
    transparent,
    #faffed66 6%,
    transparent 22%,
    #253d3218 44%,
    #ffffff7a 57%,
    transparent 68%
  );
  animation: record-spin 24s linear infinite;
  animation-play-state: var(--spin-state);
}
.record-label {
  position: absolute;
  width: 48%;
  height: 48%;
  left: 23%;
  top: 27%;
  border-radius: 50%;
  box-shadow:
    0 0 0 8px #253d328a,
    0 2px 7px #263b315e;
  background: #dce5d4;
}
.record-art-rotor {
  width: 100%;
  height: 100%;
  border-radius: inherit;
  animation: record-spin 24s linear infinite;
  animation-play-state: var(--spin-state);
}
.spindle {
  position: absolute;
  left: calc(50% - 3px);
  top: calc(50% - 3px);
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f0f4e8;
  box-shadow: 0 1px 2px #122d3555;
}
.tonearm {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  pointer-events: none;
  z-index: 3;
  filter: drop-shadow(
    2px 3px 3px rgba(35, 48, 51, 0.13)
  );
}
.tonearm-swing {
  transform-box: view-box;
  transform-origin: 378px 44px;
  transform: rotate(0deg);

  transition: transform 1050ms
    cubic-bezier(0.22, 1, 0.36, 1);
}
/* 播放时，唱针向唱片沟槽移动 */
.vinyl-playing .tonearm-swing {
  transform: rotate(10deg);
}
@media (prefers-reduced-motion: reduce) {
  .tonearm-swing {
    transition: none;
  }
}
.turntable-light {
  position: absolute;
  width: 7px;
  height: 7px;
  right: 12%;
  bottom: 10%;
  border-radius: 50%;
  background: #adc89e;
  box-shadow: 0 0 0 5px #adc89e16;
}
.vinyl-playing .turntable-light {
  background: #537951;
}
.turntable-mark {
  position: absolute;
  left: 9%;
  bottom: 5%;
  color: #819177;
  font:
    italic 18px Georgia,
    serif;
}
.vinyl-caption {
  display: flex;
  justify-content: space-between;
  margin: 28px 6px 0;
  color: var(--player-text-muted,#4d6152);
  font:
    10px Consolas,
    monospace;
  letter-spacing: 2px;
}
@keyframes record-spin {
  to {
    transform: rotate(360deg);
  }
}
/* 只改变呈现方式，保留同一个唱片、封面目标与旋转时钟。 */
.vinyl-wide-scene {
  width: 100%;
  margin: 0;
  padding: 0;
}
.vinyl-wide-scene .turntable {
  background: transparent;
  border-radius: 50%;
  box-shadow: none;
}
.vinyl-wide-scene .platter-shadow,
.vinyl-wide-scene .tonearm,
.vinyl-wide-scene .turntable-light,
.vinyl-wide-scene .turntable-mark,
.vinyl-wide-scene .vinyl-caption {
  display: none;
}
@media (max-width: 760px) {
  .vinyl-scene {
    width: min(70vw, 320px);
    padding-top: 6px;
  }
  .turntable {
    border-radius: 26px;
  }
  .vinyl-caption {
    margin-top: 18px;
    font-size: 8px;
    letter-spacing: 1px;
  }
  .vinyl-wide-scene {
    width: 100%;
    padding: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .vinyl-reflection,
  .record-art-rotor {
    animation: none;
  }
  .tonearm {
    transition: none;
  }
}
</style>

<style scoped>
@keyframes wide-ring-spin { to { transform:rotate(360deg); } }
.wide-ring-shadow, .wide-ring-rotor, .wide-ring-optics { position:absolute; inset:0; border-radius:50%; pointer-events:none; }
.wide-ring-shadow { box-shadow:-18px 60px 106px 10px #3e372f38, -7px 23px 53px #2e323b1f; }
.wide-ring-rotor { animation:wide-ring-spin 24s linear infinite; animation-play-state:var(--spin-state); }
.vinyl-wide-scene .vinyl-grooves { display:none; }
.vinyl-wide-scene .record-label { width:calc(var(--wide-cover-ratio) * 100%); height:calc(var(--wide-cover-ratio) * 100%); left:calc(50% - var(--wide-cover-ratio) * 50%); top:calc(50% - var(--wide-cover-ratio) * 50%); box-shadow:none; background:transparent; z-index:2; }
.vinyl-wide-scene .record-label::after { content:''; position:absolute; inset:0; border-radius:inherit; pointer-events:none; box-shadow:inset 0 0 4px 1px #141b2333; }
.vinyl-wide-scene .spindle { display:none; }
@media(prefers-reduced-motion:reduce) { .wide-ring-rotor { animation:none; } }
    .wide-ring-optics {
      z-index: 4;
      opacity: .84;
      --lip: calc(var(--wide-cover-ratio) * 100%);
      --seat: calc(var(--lip) + (100% - var(--lip)) * .153);
      mask-image: radial-gradient(circle closest-side,
        transparent calc(var(--lip) + .25px), #0008 calc(var(--lip) + 1.25px),
        #0008 calc(var(--seat) - 1.4px), #000 calc(var(--seat) + 1.4px),
        #000 97.5%, #000a 99.6%, transparent 100%);
      background: conic-gradient(from 0deg,
        rgb(244 246 252 / .18) 0deg,
        rgb(239 244 250 / .16) 31deg,
        rgb(238 243 250 / .02) 68deg,
        rgb(33 31 36 / .09) 117deg,
        rgb(32 31 38 / .17) 166deg,
        rgb(31 30 36 / .20) 205deg,
        rgb(32 32 40 / .17) 228deg,
        rgb(240 241 245 / 0) 250deg,
        rgb(244 244 249 / .16) 265deg,
        rgb(246 246 251 / .30) 284deg,
        rgb(245 245 250 / .27) 309deg,
        rgb(244 246 252 / .18) 360deg);
    }


</style>

<style scoped>
.vinyl-scene:not(.vinyl-wide-scene){width:min(100%,448px,48dvh);padding:30px 0 0;}
.vinyl-scene:not(.vinyl-wide-scene) .turntable{aspect-ratio:456/429;background:transparent;box-shadow:none;border-radius:0;}
.vinyl-scene:not(.vinyl-wide-scene) .platter-shadow,
.vinyl-scene:not(.vinyl-wide-scene) .vinyl-grooves,
.vinyl-scene:not(.vinyl-wide-scene) .spindle,
.vinyl-scene:not(.vinyl-wide-scene) .turntable-light{display:none;}
.vinyl-scene:not(.vinyl-wide-scene) .record-label{width:45.1916%;height:auto;aspect-ratio:1;left:27.4042%;top:25.862%;box-shadow:none;background:transparent;z-index:2;}
.classic-disc{position:absolute;width:75.44%;aspect-ratio:1;left:12.28%;top:9.786%;border-radius:50%;box-shadow:1px 3px 8px #1d22213d;}
.classic-disc::after{content:'';position:absolute;inset:16.72%;border:10px solid #55565d;border-radius:50%;}
.classic-record-rotor,.classic-gloss{position:absolute;inset:0;border-radius:50%;}
.classic-record-rotor{animation:record-spin 24s linear infinite;animation-play-state:var(--spin-state);}
.classic-gloss{mask-image:radial-gradient(circle closest-side,transparent 65.9%,#000 67%,#000 98%,transparent 100%);background:conic-gradient(from 12deg,#ffffff08,#161b231c 52deg,#fefbf92e 87deg,#ffffff08 114deg,#1f233126 154deg,#ffffff12 203deg,#ffffff2b 267deg,#ffffff08);}
@media(prefers-reduced-motion:reduce){.classic-record-rotor{animation:none;}}
</style>

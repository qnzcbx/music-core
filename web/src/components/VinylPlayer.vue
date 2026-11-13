<script setup lang="ts">
import CoverArt from "./CoverArt.vue";
import WideVinylRing from "./WideVinylRing.vue";
import { WIDE_COVER_RATIO, type RingPreset } from "./wide-vinyl/ring-field";
import type { AmbientPalette } from "../utils/ambient-palette";
import type { PlayerLayout } from "../appearance/player-layout";
import { useId, ref, watch, nextTick } from "vue";

const tonearmId = useId();
const props = defineProps<{
  cover?: string | null;
  playing: boolean;
  palette: AmbientPalette;
  label: string;
  layout?: PlayerLayout;
  ringPreset?: RingPreset;
}>();
const scene = ref<HTMLElement>();
function syncRing() {
  const cover = scene.value?.querySelector('.record-art-rotor')?.getAnimations()[0];
  const ring = scene.value?.querySelector('.wide-ring-rotor')?.getAnimations()[0];
  if (cover && ring) ring.currentTime = cover.currentTime;
}
watch(() => [props.layout, props.playing], () => { void nextTick(syncRing); });
const emit = defineEmits<{ coverElement: [element: unknown] }>();
</script>
<template>
  <div
    ref="scene"
    class="vinyl-scene"
    :class="{ 'vinyl-playing': playing, 'vinyl-wide-scene': layout === 'vinyl-wide' }"
    :style="{ '--vinyl-tint': palette.left, '--wide-cover-ratio': WIDE_COVER_RATIO, '--spin-state': playing ? 'running' : 'paused' }"
  >
    <div class="turntable" role="img" :aria-label="`${label} · ${playing ? '播放中' : '已暂停'}`">
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
            <CoverArt data-player-cover :src="cover" :alt="`${label}封面`" />
          </Teleport>
        </div>
        <i class="spindle" aria-hidden="true" />
      </div>
      <svg
        class="tonearm"
        viewBox="0 0 420 420"
        aria-hidden="true"
      >
        <defs>
          <!-- 金属管的横向反光 -->
          <linearGradient
            :id="`${tonearmId}-metal`"
            x1="366"
            y1="0"
            x2="385"
            y2="0"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0" stop-color="#747f83" />
            <stop offset=".32" stop-color="#c6ced0" />
            <stop offset=".56" stop-color="#ffffff" />
            <stop offset=".76" stop-color="#aeb9bc" />
            <stop offset="1" stop-color="#6d777c" />
          </linearGradient>

          <!-- 轴承盖，带有柔和的球面反射 -->
          <radialGradient
            :id="`${tonearmId}-bearing`"
            cx="35%"
            cy="28%"
            r="75%"
          >
            <stop offset="0" stop-color="#ffffff" />
            <stop offset=".68" stop-color="#f2f4f4" />
            <stop offset="1" stop-color="#c1c8ca" />
          </radialGradient>
        </defs>

        <!-- 固定底座：不参与旋转 -->
        <g class="tonearm-mount">
          <circle
            cx="378"
            cy="44"
            r="34"
            fill="#c5cbcd"
            opacity=".24"
          />

          <!-- 顶部金属轴 -->
          <rect
            x="366"
            y="-23"
            width="24"
            height="47"
            rx="3"
            :fill="`url(#${tonearmId}-metal)`"
          />
          <rect
            x="373"
            y="-29"
            width="10"
            height="9"
            rx="2"
            fill="#848e91"
          />
          <path
            d="M366 -7H390 M366 16H390"
            stroke="#677276"
            stroke-width="2"
            opacity=".65"
          />
        </g>

        <!-- 活动唱臂：只旋转这一组 -->
        <g class="tonearm-swing">
          <!-- 悬空投影 -->
          <path
            d="M378 44V250Q378 283 356 312L342 329"
            transform="translate(3 4)"
            fill="none"
            stroke="#42545b"
            stroke-opacity=".23"
            stroke-width="11"
            stroke-linecap="round"
          />

          <!-- 金属主管 -->
          <path
            d="M378 44V250Q378 283 356 312L342 329"
            fill="none"
            :stroke="`url(#${tonearmId}-metal)`"
            stroke-width="7"
            stroke-linecap="round"
            stroke-linejoin="round"
          />

          <!-- 沿管身的细微高光 -->
          <path
            d="M378 44V250Q378 283 356 312L342 329"
            fill="none"
            stroke="#ffffff"
            stroke-opacity=".55"
            stroke-width="1.4"
            stroke-linecap="round"
          />

          <!-- 唱头组件 -->
          <g transform="translate(342 329) rotate(35)">
            <!-- 唱臂末端的连接套 -->
            <rect
              x="-6"
              y="-9"
              width="12"
              height="14"
              rx="3"
              fill="#a5b0b3"
            />

            <!-- 唱头主体 -->
            <rect
              x="-9"
              y="-2"
              width="18"
              height="28"
              rx="7"
              fill="#edf0f0"
              stroke="#c7cfd0"
              stroke-width="1.2"
            />
            <rect
              x="-6"
              y="1"
              width="12"
              height="17"
              rx="5"
              fill="#ffffff"
              opacity=".86"
            />

            <!-- 唱针与针尖 -->
            <path
              d="M0 25V35"
              stroke="#7d898d"
              stroke-width="2"
              stroke-linecap="round"
            />
            <circle
              cx="0"
              cy="35"
              r="2"
              fill="#66787b"
            />
          </g>
        </g>

        <!-- 固定的轴承盖：覆盖活动臂的起点 -->
        <g class="tonearm-bearing">
          <circle
            cx="378"
            cy="44"
            r="22"
            :fill="`url(#${tonearmId}-bearing)`"
            stroke="#d5dadd"
          />
          <circle
            cx="378"
            cy="44"
            r="13"
            fill="#e6e9e9"
            stroke="#c7cfd0"
          />
          <circle
            cx="378"
            cy="44"
            r="6"
            fill="#f5f7f7"
            opacity=".9"
          />
        </g>
      </svg>
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

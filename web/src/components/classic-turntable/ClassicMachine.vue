<script setup lang="ts">
import { useId } from 'vue';
defineProps<{ playing: boolean; dark: boolean }>();
const id = useId();
</script>
<template>
  <div
    class="classic-machine"
    :class="{ dark, 'vinyl-playing': playing }"
  >
    <div class="turntable-deck">
      <svg
        class="deck-hardware"
        viewBox="0 0 456 429"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient
            :id="`${id}-deck-face`"
            x1="0"
            y1="0"
            x2=".92"
            y2="1"
            gradientUnits="objectBoundingBox"
          >
            <stop stop-color="var(--deck-hi)" />
            <stop
              offset=".47"
              stop-color="var(--deck-base)"
            />
            <stop
              offset="1"
              stop-color="var(--deck-lo)"
            />
          </linearGradient>
          <linearGradient
            :id="`${id}-deck-wall`"
            x1="0"
            y1="0"
            x2=".14"
            y2="1"
          >
            <stop stop-color="var(--deck-hi)" />
            <stop
              offset=".86"
              stop-color="var(--deck-base)"
            />
            <stop
              offset="1"
              stop-color="var(--deck-edge)"
            />
          </linearGradient>
          <pattern
            :id="`${id}-deck-satin`"
            patternUnits="userSpaceOnUse"
            width="3.6"
            height="5"
          >
            <path
              d="M.45 0v5M2.25 0v5"
              stroke="var(--deck-grain)"
              stroke-width=".34"
              opacity=".32"
            />
            <path
              d="M1.25 0v5M3.05 0v5"
              stroke="#fff"
              stroke-width=".26"
              opacity=".29"
            />
          </pattern>
          <linearGradient
            :id="`${id}-well-face`"
            x1="0"
            y1="0"
            x2=".68"
            y2="1"
          >
            <stop stop-color="var(--well-up)" />
            <stop
              offset="1"
              stop-color="var(--well-down)"
            />
          </linearGradient>
          <radialGradient
            :id="`${id}-well-contact`"
            cx=".49"
            cy=".49"
            r=".5"
            fx=".49"
            fy=".49"
          >
            <stop
              offset=".84"
              stop-color="#27272a"
              stop-opacity=".29"
            />
            <stop
              offset=".92"
              stop-color="#27272a"
              stop-opacity=".18"
            />
            <stop
              offset="1"
              stop-color="#27272a"
              stop-opacity="0"
            />
          </radialGradient>
          <linearGradient
            :id="`${id}-deck-top-edge`"
            x1="0"
            y1="0"
            x2=".55"
            y2="1"
          >
            <stop
              stop-color="#fff"
              stop-opacity=".88"
            />
            <stop
              offset=".6"
              stop-color="#fff"
              stop-opacity=".22"
            />
            <stop
              offset="1"
              stop-color="#fff"
              stop-opacity=".14"
            />
          </linearGradient>
        </defs>
        <rect
          x=".7"
          y="2.4"
          width="454.6"
          height="426"
          rx="44"
          :fill="`url(#${id}-deck-wall)`"
        />
        <rect
          x=".65"
          y=".65"
          width="454.7"
          height="425.4"
          rx="44"
          :fill="`url(#${id}-deck-face)`"
          :stroke="`url(#${id}-deck-top-edge)`"
          stroke-width="1.3"
        />
        <rect
          x="1.5"
          y="1.5"
          width="453"
          height="424"
          rx="43"
          :fill="`url(#${id}-deck-satin)`"
        />
        <circle
          cx="228"
          cy="214"
          r="193"
          :fill="`url(#${id}-well-face)`"
        />
        <ellipse
          cx="229"
          cy="218.5"
          rx="182.4"
          ry="183.6"
          :fill="`url(#${id}-well-contact)`"
        />
        <circle
          cx="228"
          cy="214"
          r="174"
          fill="var(--platter-rim)"
          opacity=".57"
        /></svg
      ><svg
        class="tonearm"
        viewBox="0 0 456 429"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient
            :id="`${id}-arm-seat`"
            x1="0"
            y1="0"
            x2="1"
            y2="1"
          >
            <stop stop-color="var(--seat-hi)" />
            <stop
              offset="1"
              stop-color="var(--seat-lo)"
            />
          </linearGradient>
          <linearGradient :id="`${id}-steel-lathe`">
            <stop stop-color="#a6aaa7" />
            <stop
              offset=".09"
              stop-color="#636967"
            />
            <stop
              offset=".17"
              stop-color="#919793"
            />
            <stop
              offset=".30"
              stop-color="#d3d7d3"
            />
            <stop
              offset=".45"
              stop-color="#edf0eb"
            />
            <stop
              offset=".56"
              stop-color="#b5b9b4"
            />
            <stop
              offset=".68"
              stop-color="#656b66"
            />
            <stop
              offset=".79"
              stop-color="#555a56"
            />
            <stop
              offset=".91"
              stop-color="#a8ada9"
            />
            <stop
              offset="1"
              stop-color="#c9cdc9"
            />
          </linearGradient>
          <linearGradient :id="`${id}-steel-stem`">
            <stop stop-color="#686c67" />
            <stop
              offset=".27"
              stop-color="#8e9590"
            />
            <stop
              offset=".43"
              stop-color="#f9faf6"
            />
            <stop
              offset=".66"
              stop-color="#a4a9a4"
            />
            <stop
              offset="1"
              stop-color="#4d534f"
            />
          </linearGradient>
          <linearGradient
            :id="`${id}-steel-end`"
            x1="0"
            y1="0"
            x2="0"
            y2="1"
          >
            <stop stop-color="#b8bab6" />
            <stop
              offset="1"
              stop-color="#777d78"
            />
          </linearGradient>
          <radialGradient
            :id="`${id}-arm-cap`"
            cx=".30"
            cy=".23"
            r=".86"
          >
            <stop stop-color="#fff" />
            <stop
              offset=".54"
              stop-color="#f7f7f5"
            />
            <stop
              offset=".83"
              stop-color="#e7e8e5"
            />
            <stop
              offset="1"
              stop-color="#c9ccca"
            />
          </radialGradient>
          <linearGradient
            :id="`${id}-arm-center`"
            x1="0"
            y1="0"
            x2=".74"
            y2="1"
          >
            <stop stop-color="#f8f9f7" />
            <stop
              offset="1"
              stop-color="#e5e7e4"
            />
          </linearGradient>
          <linearGradient
            :id="`${id}-head-top`"
            x1="0"
            y1="0"
            x2=".9"
            y2=".85"
          >
            <stop stop-color="#fff" />
            <stop
              offset=".44"
              stop-color="#f8f8f6"
            />
            <stop
              offset=".8"
              stop-color="#ebedea"
            />
            <stop
              offset="1"
              stop-color="#d2d5d2"
            />
          </linearGradient>
          <filter
            :id="`${id}-arm-long-shadow`"
            filterUnits="userSpaceOnUse"
            x="270"
            y="-70"
            width="260"
            height="550"
          >
            <feDropShadow
              dx="4.2"
              dy="5.4"
              stdDeviation="3.6"
              flood-color="#232827"
              flood-opacity=".27"
            />
          </filter>
          <filter
            :id="`${id}-arm-cap-shadow`"
            filterUnits="userSpaceOnUse"
            x="374"
            y="8"
            width="98"
            height="100"
          >
            <feDropShadow
              dx="3.5"
              dy="5"
              stdDeviation="3.3"
              flood-color="#212826"
              flood-opacity=".34"
            />
          </filter>
        </defs>
        <rect
          x="385.4"
          y="12.5"
          width="57.2"
          height="77.5"
          rx="28.6"
          :fill="`url(#${id}-arm-seat)`"
        />
        <g
          class="tonearm-swing"
          :filter="`url(#${id}-arm-long-shadow)`"
        >
          <!-- 配重、主轴、J 管和唱头作为同一机械件绕轴转动 -->
          <rect
            x="410.5"
            y="-29"
            width="7"
            height="59"
            rx="1"
            :fill="`url(#${id}-steel-stem)`"
          />
          <rect
            x="395.4"
            y="-20.2"
            width="37.2"
            height="25.7"
            rx="1.4"
            :fill="`url(#${id}-steel-lathe)`"
          />
          <ellipse
            cx="414"
            cy="-20.2"
            rx="18.6"
            ry="1.2"
            :fill="`url(#${id}-steel-end)`"
          />
          <path
            d="M396 -15.2h36m-36 14h36"
            stroke="#fff"
            stroke-width=".8"
            opacity=".45"
          />
          <path
            d="M395.7 -1.9h36.6M397 4.6h34"
            stroke="#3c433e"
            stroke-width=".82"
            opacity=".53"
          />
          <!-- 主弯管采用同一条连续中心线，冷银色高光一路贴着弯头 -->
          <path
            d="M414 43V254C414 286 404.5 298 384 331.8"
            fill="none"
            stroke="#656b66"
            stroke-width="7.3"
            stroke-linecap="round"
          />
          <path
            d="M413.4 43V254C413.4 285.6 403.8 298 383.4 331.8"
            fill="none"
            stroke="#b1b5b0"
            stroke-width="5.45"
            stroke-linecap="round"
          />
          <path
            d="M412.7 43V254C412.7 285.5 403 298 382.7 331.8"
            fill="none"
            stroke="#eceeea"
            stroke-width="2.9"
            stroke-linecap="round"
          />
          <path
            d="M412 43V254C412 285.5 402.6 297.6 382 331.2"
            fill="none"
            stroke="#fcfcfa"
            stroke-width=".85"
            stroke-linecap="round"
            opacity=".91"
          />
          <g transform="translate(384 331.8) rotate(32)">
            <path
              d="M5 10H36"
              fill="none"
              stroke="#a5aaa6"
              stroke-width="2.35"
              stroke-linecap="round"
            />
            <path
              d="M5 9.4H36"
              fill="none"
              stroke="#e9ebe8"
              stroke-width=".72"
              stroke-linecap="round"
            />
            <path
              d="M-3.6-5h7.2v9h-7.2z"
              :fill="`url(#${id}-steel-stem)`"
            />
            <path
              d="M-4.6 17.5h9.2v5q0 4-3.8 4h-1.6q-3.8 0-3.8-4z"
              fill="#969b95"
            />
            <path
              d="M-.7 24.4 0 27.5l1.15-3.1"
              fill="#555b55"
            />
            <rect
              x="-11"
              y="-11.3"
              width="22"
              height="36.2"
              rx="11"
              :fill="`url(#${id}-head-top)`"
            />
            <path
              d="M-9-1a9 9 0 0 1 9-9"
              fill="none"
              stroke="#fff"
              opacity=".6"
              stroke-width=".72"
            />
            <circle
              cx="0"
              cy="11.9"
              r="4.25"
              :fill="`url(#${id}-arm-center)`"
              stroke="#cbd0cc"
              stroke-width=".75"
            />
          </g>
        </g>
        <g :filter="`url(#${id}-arm-cap-shadow)`">
          <circle
            cx="414"
            cy="43"
            r="19.3"
            :fill="`url(#${id}-arm-cap)`"
          />
          <circle
            cx="414"
            cy="43"
            r="10.3"
            :fill="`url(#${id}-arm-center)`"
            stroke="#c7cdc8"
            stroke-width=".8"
          />
          <path
            d="M404 44a10.1 10.1 0 0 1 10-11.2"
            stroke="#fff"
            stroke-width=".72"
            fill="none"
            opacity=".8"
          />
        </g>
      </svg>
    </div>
  </div>
</template>
<style scoped>
.classic-machine {
  --deck-hi: #fff;
  --deck-base: #fafafa;
  --deck-lo: #f8f8f7;
  --deck-edge: #dadbd7;
  --deck-grain: #a0a5a0;
  --well-up: #ededeb;
  --well-down: #f0f0ee;
  --platter-rim: #d2d3d1;
  --seat-hi: #e7e7e5;
  --seat-lo: #eeeeec;
  --arm-angle: 0deg;
  position: relative;
  width: 100%;
  height: 100%;

  margin: 0 auto;
  isolation: auto;
}
.classic-machine.dark {
  --deck-hi: #414b54;
  --deck-base: #343d46;
  --deck-lo: #2d363f;
  --deck-edge: #171e26;
  --deck-grain: #717e87;
  --well-up: #292f38;
  --well-down: #323b45;
  --platter-rim: #46505b;
  --seat-hi: #262e36;
  --seat-lo: #303a43;
}
.turntable-deck {
  position: absolute;
  inset: 0;
}
.turntable-deck::before {
  content: '';
  position: absolute;
  inset: 1% 1% 0 1%;
  border-radius: 10.6%;
  box-shadow:
    21px 29px 36px -12px rgb(48 46 72 / 0.18),
    4px 8px 13px -3px rgb(48 46 64 / 0.11);
  pointer-events: none;
}
.dark .turntable-deck::before {
  box-shadow:
    22px 29px 43px -11px rgb(0 0 0 / 0.45),
    4px 9px 17px -4px rgb(0 0 0 / 0.3);
}
.deck-hardware,
.tonearm {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  overflow: visible;
  pointer-events: none;
}
.tonearm {
  z-index: 8;
}
.tonearm-swing {
  transform-box: view-box;
  transform-origin: 414px 43px;
  transform: rotate(var(--arm-angle));
  transition: transform 780ms cubic-bezier(0.25, 0.72, 0.26, 1);
}
.vinyl-playing {
  --arm-angle: 8deg;
}

.classic-machine {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
@media (prefers-reduced-motion: reduce) {
  .tonearm-swing {
    transition: none;
  }
}
</style>

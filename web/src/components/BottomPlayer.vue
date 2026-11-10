<script setup lang="ts">
import {computed,onMounted,ref} from 'vue';
import {useCoreClient} from '../composables/useCoreClient';
import {usePlayerVisuals} from '../composables/usePlayerTransition';
import CoverArt from './CoverArt.vue';
import PlayIcon from '~icons/lucide/play';
import PauseIcon from '~icons/lucide/pause';
import PreviousIcon from '~icons/lucide/skip-back';
import NextIcon from '~icons/lucide/skip-forward';
import PlaybackModeMenu from './player/PlaybackModeMenu.vue';
import VolumePopover from './player/VolumePopover.vue';
import QueuePanel from './player/QueuePanel.vue';
import '../styles/player-layers.css';
const {player}=useCoreClient();
const props=defineProps<{immersive?:boolean}>();
const visuals=usePlayerVisuals();
const {selected,time,duration,playing,message,phase}=player;
const host=ref<HTMLElement>(),preview=ref<number|null>(null);
onMounted(()=>{if(!props.immersive&&host.value){visuals.setMiniFooter(host.value);visuals.setMiniCover(host.value.querySelector('.mini-cover-art'));}});
const progress=computed(()=>preview.value??time.value);
const pauseAction=computed(()=>['opening','positioning'].includes(phase.value)?player.playIntent.value:playing.value);
const format=(value:number)=>`${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}`;
function seek(event:Event){player.seek(Number((event.target as HTMLInputElement).value));preview.value=null;}
</script>
<template>
<footer ref="host" class="player" :class="{'immersive-controls':immersive}" :data-phase="phase">
 <div class="player-info"><button class="player-cover" :disabled="!selected" title="打开沉浸式播放器" aria-label="打开沉浸式播放器" @click="visuals.open"><span class="mini-cover-art"><CoverArt :src="selected?.cover"/></span></button>
 <div class="player-meta"><span class="track-title">{{selected?.title||selected?.name||'选择歌曲开始播放'}}</span><span class="player-artist">{{selected?.artist||(selected?'':'从搜索结果选择具体版本')}}</span><span class="player-album">{{selected?.album}}</span><span class="playback-status" :class="{'notice-visible':['opening','positioning','error','blocked','network'].includes(phase)}" role="status">{{message}}</span></div></div>
 <div class="transport"><div class="transport-buttons">
  <PlaybackModeMenu/><button aria-label="上一首" :disabled="!player.queue.hasPrevious.value" @click="player.queue.previous"><PreviousIcon/></button>
  <button class="play-toggle" :disabled="!selected" :aria-label="pauseAction?'暂停':'播放'" @click="player.toggle"><PauseIcon v-if="pauseAction"/><PlayIcon v-else/></button>
  <button aria-label="下一首" :disabled="!player.queue.hasNext.value" @click="player.queue.next"><NextIcon/></button><VolumePopover/>
 </div><div class="progress-row"><time>{{format(progress)}}</time><input aria-label="播放进度" type="range" min="0" :max="duration" step="0.1" :value="progress" :disabled="!selected||duration<=0" @input="preview=Number(($event.target as HTMLInputElement).value)" @change="seek" @blur="preview=null"/><time>{{duration?format(duration):'—:—'}}</time></div></div>
 <div class="player-tools"><button v-if="selected" @click="player.retry" aria-label="重试播放">重试</button><button v-if="selected" @click="player.stop" aria-label="关闭播放">关闭</button><button v-if="!immersive" :disabled="!selected" title="查看歌词" aria-label="查看歌词" @click="visuals.open">词</button><QueuePanel/></div>
</footer>
</template>
<style scoped>
.player-meta .playback-status.notice-visible{position:static;display:block;width:auto;height:auto;clip-path:none;font-size:11px;color:var(--app-text-muted);}
.player {
  z-index: 20;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 1.4fr) minmax(0, 1fr);
  align-items: center;
  gap: 24px;
  border-top-width: 1px;
}
.player :deep(button) {
  cursor: pointer;
  color: var(--mini-text);
  background: transparent;
  border: 0;
}
.player :deep(button):disabled {
  cursor: default;
  opacity: 0.4;
}
.player :deep(button):focus-visible {
  outline: 2px solid var(--mini-accent);
  outline-offset: 3px;
}
.player :deep(svg) {
  width: 19px;
  height: 19px;
}
.player-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.player-cover {
  position: relative;
  padding: 0;
  border-radius: 8px;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  overflow: hidden;
  background: var(--mini-surface);
}
.mini-cover-art {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 8px;
}
.player-meta {
  min-width: 0;
}
.track-title {
  display: block;
  max-width: 100%;
  padding: 0;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  text-align: left;
}
.player-meta :is(.track-title, .player-artist, .player-album) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.player-meta > span {
  display: block;
  color: var(--mini-muted);
  font-size: 11px;
  line-height: 1.6;
}
.player-meta .playback-status {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
.transport {
  min-width: 0;
}
.transport-buttons {
  display: flex;
  justify-content: center;
  gap: 18px;
  align-items: center;
}
.transport-buttons :deep(button),
.player-tools :deep(button) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  border-radius: 8px;
  min-width: 36px;
  height: 36px;
}
.transport-buttons :deep(button):hover:not(:disabled),
.player-tools :deep(button):hover:not(:disabled),
.player :deep(button)[aria-expanded="true"] {
  background: color-mix(in srgb, var(--mini-text) 12%, transparent);
}
.transport-buttons .play-toggle {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--mini-button);
  color: var(--mini-button-text);
}
.transport-buttons .play-toggle:hover:not(:disabled) {
  background: var(--mini-button);
  filter: brightness(1.12);
}
.progress-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 6px;
}
.progress-row input {
  min-width: 0;
  flex: 1;
  accent-color: var(--mini-accent);
  height: 16px;
  cursor: pointer;
}
.progress-row time {
  font:
    10px Consolas,
    monospace;
  color: var(--mini-muted);
  min-width: 30px;
}
.progress-row time:last-child {
  text-align: right;
}
.player-tools {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 8px;
}
.player-tools :deep(button) {
  gap: 5px;
  font: inherit;
  font-size: 14px;
}
.queue-count {
  font-size: 10px;
  color: var(--mini-muted);
}
.player-immersive .mini-cover-art {
  opacity: 0;
}
.mini-collapse {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font:
    30px Georgia,
    serif;
}
.player-immersive {
  background: var(--mini-bg-immersive);
}
@container player-workspace (max-width: 860px) {
  .player {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px 12px;
  }
  .transport {
    grid-column: 1/-1;
    grid-row: 2;
  }
  .player-tools {
    grid-column: 2;
    grid-row: 1;
  }
  .player-cover {
    width: 44px;
    height: 44px;
  }
  .player-album {
    display: none !important;
  }
  .transport-buttons {
    gap: 18px;
  }
}
@media (max-width: 600px) {
  .player {
    gap: 6px 8px;
  }
  .player-info {
    gap: 8px;
  }
  .player-tools {
    gap: 0;
  }
  .player-tools :deep(button) {
    padding: 6px;
  }
  .transport-buttons :deep(button) {
    min-width: 40px;
    height: 40px;
  }
  .transport-buttons {
    gap: 12px;
  }
}
</style>
<style scoped>
.immersive-controls{position:fixed;inset:auto 0 0;z-index:25;grid-template-columns:minmax(0,1fr) minmax(280px,540px) minmax(0,1fr);padding:14px 28px max(14px,env(safe-area-inset-bottom));background:var(--mini-bg-immersive);color:var(--mini-text);backdrop-filter:blur(16px);--mini-text:#f0f2e5;--mini-muted:#c3cfc0;--mini-accent:#bbd2a8;--mini-button:#e4ecd8;--mini-button-text:#24432f;--mini-surface:#365644}
.immersive-controls .player-cover{display:none}
@media(max-width:760px){.immersive-controls{grid-template-columns:minmax(0,1fr) auto;padding:10px 12px max(10px,env(safe-area-inset-bottom))}.immersive-controls .player-info{grid-column:1;grid-row:1}.immersive-controls .transport{grid-column:1/-1;grid-row:2}.immersive-controls .player-tools{grid-column:2;grid-row:1}}
</style>

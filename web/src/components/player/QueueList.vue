<script setup lang="ts">
import {useCoreClient} from '../../composables/useCoreClient';
import CoverArt from '../CoverArt.vue';
const {player}=useCoreClient();const {entries,current}=player.queue;
</script>
<template><div class="queue-list"><header><span>{{entries.length}} 首 · {{({order:'顺序播放',shuffle:'随机播放',repeat_all:'列表循环',repeat_one:'单曲循环'})[player.queue.navigation.mode]}}</span><button @click="player.queue.clearPending">清空待播</button></header><p v-if="!entries.length">队列还是空的</p><article v-for="entry in entries" :key="entry.key" :data-current="entry.key===current"><div class="queue-cover"><CoverArt :src="entry.metadata.cover"/></div><button class="queue-choose" @click="entry.key===current&&player.selected.value?player.toggle():player.queue.choose(entry)"><strong>{{entry.metadata.title}}</strong><small>{{entry.metadata.artist}} · {{entry.track.providerId}}{{entry.key===current?' · 当前':''}}</small></button><button :aria-label="`移除 ${entry.metadata.title}`" @click="player.queue.remove(entry.key)">×</button></article></div></template>

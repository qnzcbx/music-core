<script setup lang="ts">
import {DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem} from '../ui/dropdown-menu';
import {useCoreClient} from '../../composables/useCoreClient';
import OrderIcon from '~icons/lucide/list-ordered';
import ShuffleIcon from '~icons/lucide/shuffle';
import RepeatIcon from '~icons/lucide/repeat';
import RepeatOneIcon from '~icons/lucide/repeat-1';
const {player}=useCoreClient();
const modes=[{id:'order',label:'顺序播放',icon:OrderIcon},{id:'shuffle',label:'随机播放',icon:ShuffleIcon},{id:'repeat_one',label:'单曲循环',icon:RepeatOneIcon},{id:'repeat_all',label:'列表循环',icon:RepeatIcon}] as const;
</script>
<template><DropdownMenu><DropdownMenuTrigger as-child><button aria-label="播放模式" :title="modes.find(m=>m.id===player.queue.navigation.mode)?.label"><component :is="modes.find(m=>m.id===player.queue.navigation.mode)?.icon"/></button></DropdownMenuTrigger><DropdownMenuContent class="music-layer" side="top" :side-offset="12"><DropdownMenuItem v-for="mode in modes" :key="mode.id" :data-selected="player.queue.navigation.mode===mode.id" @select="player.queue.setMode(mode.id)"><component :is="mode.icon"/>{{mode.label}}<span v-if="player.queue.navigation.mode===mode.id">✓</span></DropdownMenuItem></DropdownMenuContent></DropdownMenu></template>

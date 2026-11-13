import { computed, reactive, toRefs } from 'vue';
import type { QueueEntry, Song } from '../types/music';
import { queueEntryFrom, queueKey } from '../utils/player-queue.ts';
import { createQueueNavigation } from '../player/queue-navigation.ts';
import { MAX_QUEUE, type PersistedPlayer } from '../player/player-persistence.ts';

/** 单个浏览器页面会话共享，不持久化已过期的后端歌曲 ID。 */
const state = reactive({
  currentQueueKey: null as string | null,
  queue: [] as QueueEntry[],
  playing: false,
  currentTime: 0,
  duration: 0,
  volume: 1,
  navigation: createQueueNavigation(),
});

export function usePlayerStore() {
  const currentEntry=computed(()=>state.queue.find(entry=>entry.key===state.currentQueueKey));
  const currentSong=computed(()=>currentEntry.value?.resolved??null);
  function upsert(entry:QueueEntry,song?:Song) {
    if(entry.key!==queueKey(entry.track))throw new Error('无效队列身份');
    const held=state.queue.find(item=>item.key===entry.key);
    if(held){held.metadata={...entry.metadata};if(song)held.resolved=song;return held;}
    const added={key:entry.key,track:{...entry.track},metadata:{...entry.metadata},...(song?{resolved:song}:{})};
    state.queue.push(added);return added;
  }
  function select(song: Song, entry=queueEntryFrom(song)) {
    upsert(entry,song);
    state.currentQueueKey=entry.key;
  }
  function alignUpNext() {
    const waiting=new Set(state.navigation.upNextKeys);
    const pending=state.navigation.upNextKeys.map(key=>state.queue.find(entry=>entry.key===key)).filter((entry):entry is QueueEntry=>!!entry);
    if(!pending.length)return;
    const ordinary=state.queue.filter(entry=>!waiting.has(entry.key));
    const index=ordinary.findIndex(entry=>entry.key===state.currentQueueKey);
    const ordered=[...ordinary.slice(0,index+1),...pending,...ordinary.slice(index+1)];
    if(ordered.some((entry,index)=>entry.key!==state.queue[index]?.key))state.queue=ordered;
  }
  function scheduleNext(entry:QueueEntry) {
    if(entry.key===state.currentQueueKey)return false;
    if(!state.queue.some(item=>item.key===entry.key)&&state.queue.length>=MAX_QUEUE)throw new Error(`播放列表最多保存${MAX_QUEUE}首，请先移除部分歌曲`);
    upsert(entry);
    state.navigation.upNextKeys=[entry.key,...state.navigation.upNextKeys.filter(key=>key!==entry.key)];
    alignUpNext();return true;
  }
  function clear() { state.currentQueueKey = null; }
  function replaceCurrent(queueKey:string,mediaId:string,song:Song) {
    const entry=currentEntry.value;
    if(state.currentQueueKey!==queueKey||!entry||entry.resolved?.id!==mediaId)return false;
    entry.resolved=song;
    return true;
  }
  function remove(key:string) {
    const index=state.queue.findIndex(entry=>entry.key===key);
    if(index<0)return;
    const [entry]=state.queue.splice(index,1);if(entry)delete entry.resolved;
    if(state.currentQueueKey===key)state.currentQueueKey=null;
    state.navigation.sync(state.queue.map(entry=>entry.key),state.currentQueueKey);
    return index;
  }
  function clearQueue() {
    state.queue.forEach(entry=>{delete entry.resolved;});
    state.queue=[];state.currentQueueKey=null;state.navigation.reset();
  }
  function restoreQueue(saved:PersistedPlayer) {
    state.queue=saved.queue
      .filter((entry):entry is QueueEntry=>!('kind' in entry))
      .map(entry=>({key:entry.key,track:{...entry.track},metadata:{...entry.metadata}}));
    state.currentQueueKey=saved.currentQueueKey;
    state.playing=false;state.currentTime=0;state.duration=0;state.volume=saved.settings.volume;
    state.navigation.reset();state.navigation.mode=saved.navigation.mode;
    state.navigation.knownKeys=state.queue.map(entry=>entry.key);
    state.navigation.bag=[...saved.navigation.bag];state.navigation.history=[...saved.navigation.history];state.navigation.historyIndex=saved.navigation.historyIndex;
    state.navigation.upNextKeys=[...saved.navigation.upNextKeys];alignUpNext();
  }
  return { ...toRefs(state), currentSong, currentEntry, select, clear, replaceCurrent, remove, clearQueue, restoreQueue, scheduleNext, alignUpNext };
}

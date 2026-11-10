export type PlaybackMode = 'order' | 'shuffle' | 'repeat_all' | 'repeat_one';
export interface QueueStep { key: string; historyIndex?: number; priority?: boolean }

/** Queue-owned navigation state. Planning never commits a failed selection. */
export function createQueueNavigation(random = Math.random) {
  let pendingShuffle: { signature: string; bag: string[] } | undefined;
  return {
    mode: 'order' as PlaybackMode,
    bag: [] as string[],
    upNextKeys: [] as string[],
    history: [] as string[],
    historyIndex: -1,
    knownKeys: [] as string[],
    shuffled(keys: string[]) {
      const result = [...keys];
      for (let i = result.length - 1; i > 0; i--) {
        const j = Math.floor(random() * (i + 1));
        [result[i], result[j]] = [result[j]!, result[i]!];
      }
      return result;
    },
    sync(keys: string[], current: string | null) {
      const valid = new Set(keys), added = keys.filter(key => !this.knownKeys.includes(key));
      this.bag = this.bag.filter(key => valid.has(key));
      this.upNextKeys = [...new Set(this.upNextKeys.filter(key=>valid.has(key)))];
      const before = this.history.slice(0, this.historyIndex + 1).filter(key => valid.has(key)).length;
      this.history = this.history.filter(key => valid.has(key));
      this.historyIndex = before - 1;
      if (this.mode === 'shuffle') this.bag.push(...this.shuffled(added.filter(key => key !== current)));
      this.knownKeys = [...keys];
    },
    setMode(mode: PlaybackMode, keys: string[], current: string | null) {
      if (!['order', 'shuffle', 'repeat_all', 'repeat_one'].includes(mode)) return;
      if (this.mode === mode) return;
      this.sync(keys, current);
      this.mode = mode;
      this.bag = mode === 'shuffle' ? this.shuffled(keys.filter(key => key !== current)) : [];
    },
    visit(key: string, historyIndex?: number) {
      if (historyIndex !== undefined && this.history[historyIndex] === key) this.historyIndex = historyIndex;
      else if (this.history[this.historyIndex] !== key) {
        this.history = this.history.slice(0, this.historyIndex + 1);
        this.history.push(key); this.historyIndex = this.history.length - 1;
      }
      this.bag = this.bag.filter(item => item !== key);
      this.upNextKeys = this.upNextKeys.filter(item=>item!==key);
    },
    previous(current?: string | null): QueueStep | undefined {
      // A bound-but-unplayable selection is not in history: return the last
      // successful selection instead of skipping it or disabling previous.
      const index = current !== undefined && this.history[this.historyIndex] !== current ? this.historyIndex : this.historyIndex - 1;
      return index >= 0 ? { key: this.history[index]!, historyIndex: index } : undefined;
    },
    preview(keys: string[], current: string | null, ended = true): QueueStep | undefined {
      return this.next(keys, current, ended, undefined, true);
    },
    next(keys: string[], current: string | null, ended = false, removedIndex?: number, preview = false): QueueStep | undefined {
      if (!keys.length) return;
      if (ended && this.mode === 'repeat_one' && current) return { key: current };
      if (this.upNextKeys[0]) return { key:this.upNextKeys[0],priority:true };
      if (removedIndex === undefined && this.historyIndex < this.history.length - 1) {
        const index = this.historyIndex + 1;
        return { key: this.history[index]!, historyIndex: index };
      }
      if (this.mode === 'shuffle') {
        if (this.bag.length) return { key: this.bag[0]! };
        const signature = JSON.stringify([keys, current, this.mode, this.history, this.historyIndex, this.upNextKeys]);
        if (pendingShuffle?.signature !== signature)
          pendingShuffle = { signature, bag: this.shuffled(keys.filter(key => key !== current)) };
        if (!preview) this.bag = [...pendingShuffle.bag];
        return { key: pendingShuffle.bag[0] ?? keys[0]! };
      }
      if (removedIndex !== undefined) return { key: keys[removedIndex % keys.length]! };
      const index = current ? keys.indexOf(current) : -1;
      if (index < keys.length - 1) return { key: keys[index + 1]! };
      if (this.mode !== 'order') return { key: keys[0]! };
    },
    reset() { pendingShuffle = undefined; this.bag = []; this.upNextKeys = []; this.history = []; this.historyIndex = -1; this.knownKeys = []; },
  };
}

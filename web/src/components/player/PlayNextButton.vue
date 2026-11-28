<script setup lang="ts">
import { nextTick, onScopeDispose } from 'vue';
import gsap from 'gsap';
import ListPlus from '~icons/lucide/list-plus';
import { useCoreClient } from '../../composables/useCoreClient';
import type { PlayableSong } from '../../types/music';

const props = defineProps<{ song: PlayableSong; disabled?: boolean }>();
const { player } = useCoreClient();
const animations = new Set<() => void>();
let disposed = false;
onScopeDispose(() => {
  disposed = true;
  animations.forEach((cancel) => cancel());
});

async function enqueue(event: MouseEvent) {
  if (!player.queue.playNext(props.song)) return;
  const from = (event.currentTarget as HTMLElement).getBoundingClientRect();
  await nextTick();
  if (disposed) return;
  const target = Array.from(document.querySelectorAll<HTMLButtonElement>('[data-queue-trigger]'))
    .find((button) => button.getClientRects().length > 0);
  if (!target) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const receive = () => {
    if (!target.isConnected) return;
    const icon = target.querySelector('svg');
    if (!icon) return;
    const tween = gsap.fromTo(icon,
      reduced ? { opacity: .55 } : { scale: 1.16 },
      { opacity: 1, scale: 1, duration: .21, ease: 'power2.out', overwrite: 'auto',
        clearProps: 'transform,opacity',
        onInterrupt: () => animations.delete(cancel),
        onComplete: () => animations.delete(cancel) },
    );
    const cancel = () => { tween.kill(); gsap.set(icon, { clearProps: 'transform,opacity' }); };
    animations.add(cancel);
  };
  if (reduced) { receive(); return; }

  const to = target.getBoundingClientRect();
  const x = from.left + from.width / 2, y = from.top + from.height / 2;
  const dx = to.left + to.width / 2 - x, dy = to.top + to.height / 2 - y;
  const lift = Math.min(160, Math.max(42, Math.hypot(dx, dy) * .23));
  const tile = document.createElement('span');
  tile.className = 'queue-flight';
  tile.setAttribute('aria-hidden', 'true');
  tile.textContent = '♫';
  if (props.song.cover) {
    const cover = document.createElement('img');
    cover.alt = '';
    cover.referrerPolicy = 'no-referrer';
    cover.src = props.song.cover;
    cover.onerror = () => cover.remove();
    tile.append(cover);
  }
  document.body.append(tile);
  gsap.set(tile, { x: x - 18, y: y - 18 });
  const progress = { value: 0 };
  const tween = gsap.to(progress, {
    value: 1, duration: .58, ease: 'power1.inOut',
    onUpdate() {
      const t = progress.value;
      gsap.set(tile, { x: x - 18 + dx * t, y: y - 18 + dy * t - 2 * lift * t * (1 - t),
        scale: 1 - .68 * t, opacity: Math.min(1, (1 - t) / .28) });
    },
    onComplete() { tile.remove(); animations.delete(cancel); receive(); },
  });
  const cancel = () => { tween.kill(); tile.remove(); };
  animations.add(cancel);
}
</script>

<template>
  <button type="button" title="下一首播放" aria-label="下一首播放" :disabled="disabled" @click.stop="enqueue">
    <ListPlus aria-hidden="true" />
  </button>
</template>

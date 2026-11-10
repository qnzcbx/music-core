import { nextTick, type Ref } from 'vue';
import gsap from 'gsap';
import { Flip } from 'gsap/Flip';
import type { PlayerLayout } from '../appearance/player-layout';

export type PlayerVisualPhase = 'idle' | 'opening' | 'closing' | 'layout';

/** Geometry only. The root coordinates this owner with the mini/large flight. */
export function createPlayerLayoutTransition(
  panel: Ref<HTMLElement | undefined>,
  reduced: Ref<boolean>,
  phase: Ref<PlayerVisualPhase>,
) {
  let generation = 0;
  let context = gsap.context(() => {});
  let restoreCapturedStyles: (() => void) | undefined;
  function cancel() {
    generation++;
    context.revert();
    restoreCapturedStyles?.();
    restoreCapturedStyles = undefined;
    context = gsap.context(() => {});
    if (phase.value === 'layout') phase.value = 'idle';
  }
  function capture(nextLayout: PlayerLayout) {
    const host = panel.value;
    if (reduced.value || !host?.isConnected) return;
    // Never animate the rotor/reflection: their transform belongs to CSS spin.
    const record = host.querySelector<HTMLElement>('.turntable');
    const cover = host.querySelector<HTMLElement>('[data-cover-role=large]');
    const reading = host.querySelector<HTMLElement>('.listening-column');
    const vinylPair = (host.classList.contains('classic-layout') || host.classList.contains('wide-layout')) &&
      (nextLayout === 'classic' || nextLayout === 'vinyl-wide');
    const targets = [record, cover, reading].filter((node): node is HTMLElement => !!node);
    const measured = vinylPair ? targets : [reading].filter((node): node is HTMLElement => !!node);
    if (!reading || (vinylPair && targets.length !== 3) || measured.some(node => {
      const box = node.getBoundingClientRect();
      return !Number.isFinite(box.x + box.y + box.width + box.height) || box.width <= 1 || box.height <= 1;
    })) return;
    const surface = host.querySelector<HTMLElement>('.square-cover-surface');
    const styles = [...targets, ...(surface ? [surface] : [])].map(node => [node, node.getAttribute('style')] as const);
    restoreCapturedStyles = () => {
      for (const [node, style] of styles) {
        if (style === null) node.removeAttribute('style');
        else node.setAttribute('style', style);
      }
    };
    const desktop = vinylPair && window.innerWidth >= 1024 && window.innerHeight >= 650;
    let first: ReturnType<typeof Flip.getState> | undefined;
    try { if (desktop) first = Flip.getState(targets, { props: 'borderRadius,backgroundColor' }); }
    catch { cancel(); return; }
    return {
      token: ++generation, host, targets,
      first, desktop, nextLayout, reading,
    };
  }
  async function play(work: ReturnType<typeof capture>) {
    if (!work) return;
    phase.value = 'layout';
    await nextTick();
    if (work.token !== generation) return;
    if (reduced.value || panel.value !== work.host || !work.host.isConnected) { cancel(); return; }
    const done = () => { if (work.token === generation) cancel(); };
    context.add(() => {
      if (work.desktop) {
        // Last is now measured from Vue's final CSS (including fixed parents).
        // Nested cover correction prevents the record scale being applied twice.
        const motion = Flip.from(work.first!, {
          duration: 0.76, ease: 'power2.inOut', scale: true,
          nested: true, absolute: false, onComplete: done,
        });
        // Reflow once into the destination; soften text while the columns cross.
        motion.to(work.targets[2]!, { opacity: 0.5, duration: 0.2 }, 0)
          .to(work.targets[2]!, { opacity: 1, duration: 0.32 }, 0.44);
        if (!work.host.classList.contains('wide-layout')) {
          const details = work.host.querySelectorAll('.tonearm, .turntable-mark, .turntable-light, .vinyl-caption');
          motion.fromTo(details, { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0.46);
        }
      } else {
        // New templates have different/no cover surfaces: never invent a target.
        const surface = work.nextLayout === 'lyrics-only' ? null : work.host.querySelector<HTMLElement>(
          work.nextLayout === 'square-cover' ? '.square-cover-surface' : '.turntable');
        gsap.fromTo([work.reading, ...(surface ? [surface] : [])], { opacity: 0.72, y: 6 }, {
          opacity: 1, y: 0, duration: 0.22, ease: 'power2.out', onComplete: done,
        });
      }
    });
  }
  function dispose() { cancel(); context.revert(); }
  return { capture, play, cancel, dispose };
}

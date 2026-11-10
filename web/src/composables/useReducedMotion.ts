import { onUnmounted, ref } from 'vue';
export function useReducedMotion() {
  const media=window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduced=ref(media.matches);
  const changed=()=>{reduced.value=media.matches;};
  media.addEventListener('change',changed);
  onUnmounted(()=>media.removeEventListener('change',changed));
  return reduced;
}

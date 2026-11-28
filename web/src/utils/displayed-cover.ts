export const CLOVER_COVER = '/ambient-covers/four_leaf_clover.svg';
export type CoverLoad = 'pending' | 'loaded' | 'failed';

export function displayedCover(
  src: string | null | undefined,
  state: CoverLoad,
  fallback: boolean,
  fallbackLoaded: boolean,
) {
  if (src && state === 'loaded') return src;
  return (!src || state === 'failed') && fallback && fallbackLoaded ? CLOVER_COVER : null;
}

import type { RGB } from '../../utils/ambient-palette';
export const neutralMaterial: { neutral: number[]; inside: number[][]; outside: number[][] };
export function coverSamples(image: HTMLImageElement, palette: typeof neutralMaterial): RGB[];
export function paintRecord(
  ctx: CanvasRenderingContext2D,
  size: number,
  palette: typeof neutralMaterial,
  settings: { opacity: number; blur: number },
  custom: readonly RGB[],
): void;

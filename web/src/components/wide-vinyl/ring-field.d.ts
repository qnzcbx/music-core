import type { RingPreset } from '../../appearance/player-layout';
export type { RingPreset } from '../../appearance/player-layout';
export const WIDE_COVER_RATIO: number;
export interface RingField {
  size: number;
  ratio: number;
  radiusIdx: Uint16Array;
  flow: Float32Array;
  grooveLight: Float32Array;
  edge: Uint8Array;
  pixels: ImageData;
}
export const VINYL_PRESETS: Record<
  RingPreset,
  {
    name: string;
    baseRGB: number[];
    collarRGB: number[];
    rimRGB: number[];
    alphaOuter: number;
    alphaCollar: number;
  }
>;
export function buildRingField(size: number, ratio: number): RingField;
export function paintRing(
  ctx: CanvasRenderingContext2D,
  field: RingField,
  preset: RingPreset,
): void;

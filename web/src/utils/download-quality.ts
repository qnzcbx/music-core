import type { MediaRepresentation } from '../types/core';

export function downloadQualitySummary(media: MediaRepresentation | null | undefined): string {
  if (!media) return '';
  const parts: string[] = [];
  const format = media.codec || media.container;
  if (format) parts.push(format.toUpperCase());
  if (media.bitrateBps && media.bitrateBps > 0) {
    parts.push(`${Math.round(media.bitrateBps / 1000)} kbps`);
  }
  // sizeBytes 来自媒体完整响应长度或 Content-Range 总长，不使用前缀接收量。
  if (media.sizeBytes && media.sizeBytes > 0) {
    parts.push(`${(media.sizeBytes / 1048576).toFixed(1)} MB`);
  }
  return parts.join(' · ');
}

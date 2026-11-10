export type DownloadOptionOrigin = 'provider_exact' | 'current_resolved_media';
export interface DownloadQualityOption {
  id: string;
  origin: DownloadOptionOrigin;
  tier: 'lossless' | 'high' | 'standard' | 'unknown';
  label: string;
  providerQualityId: string;
  requestedProviderQualityId: string | null;
  sampleRate: number | null;
  bitDepth: number | null;
  container: string | null;
  codec: string | null;
  bitrate: number | null;
  lossless: boolean | null;
  sizeBytes: number | null;
  sizeKind: 'measured' | 'estimated' | 'unknown';
  sizeEvidence: string;
  availability: 'available' | 'stale';
  evidence: string;
  resolverRoute: string;
  /** 已通过既有应用下载准入，不等于另行授予媒体许可。 */
  downloadAllowed: boolean;
}

export interface DownloadOptionsJob {
  id: string;
  state: 'checking' | 'completed';
  candidateId: string;
  source: string;
  options: DownloadQualityOption[];
  checks: { origin: DownloadOptionOrigin; providerQualityId: string; availability: 'checking' | 'unknown' | 'available' | 'unavailable' | 'stale'; reason: string }[];
  elapsedMs: number;
  scope: string;
}

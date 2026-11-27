export type QualityPolicy = 'auto' | 'space_saving' | 'balanced' | 'lossless_preferred';
export type CandidateAvailability =
  | 'unknown'
  | 'queued'
  | 'resolving'
  | 'ready'
  | 'failed'
  | 'stale'
  | 'timeout'
  | 'unsupported';

export interface AccessDecision {
  state: 'allowed' | 'denied' | 'unknown';
  reason: string;
  evidence: string;
}
export interface TrackContract {
  trackAccess?: {
    playback: AccessDecision;
    download: AccessDecision;
    facts?: {
      evidence: string;
      is_streamable: boolean | null;
      is_downloadable: boolean | null;
      is_stream_gated: boolean | null;
      is_download_gated: boolean | null;
      stream_conditions_present: boolean | null;
      download_conditions_present: boolean | null;
    } | null;
  };
  license?: { id: string | null; url: string | null; conditions: string[]; evidence: string };
  credits?: { name: string; role: 'credited_artist' | 'uploader' | 'unknown'; evidence: string }[];
  recordingIdentity?: import('./core').TrackIdentity;
  metadataSource?: string;
}
export interface MediaVariant {
  providerQualityId: string;
  requestedProviderQualityId: string;
  container: string | null;
  codec: string | null;
  bitrate: number | null;
  sampleRate: number | null;
  bitDepth: number | null;
  lossless: boolean | null;
  sizeBytes: number | null;
  estimatedSizeBytes: number | null;
  evidence: string;
}

export interface Song extends TrackContract {
  mediaCheckedAt?: number;
  mediaValidUntil?: number;
  mediaProtocol?: 'progressive';
  observedProtocols?: string[];
  streamSnipped?: boolean;
  providerId?: string;
  candidateId?: string;
  qualityPolicy?: QualityPolicy;
  variant?: MediaVariant;
  id: string;
  mid: string;
  name: string;
  title?: string;
  artist: string;
  album: string;
  duration: string;
  cover: string | null;
  ext: string;
  playable: boolean;
  source: string;
  resolver: string;
  probe_ok: boolean;
  probe_status: number | null;
  probe_method: string;
  media_host: string;
}

// 候选与媒体记录是两个领域对象；候选没有已确认的格式或可播放标记。
export interface CandidateRow extends TrackContract {
  identity: import('./core').TrackIdentity;
  resolvingBackground?: boolean;
  availability?: CandidateAvailability;
  availabilityValidUntil?: number;
  id: string;
  source: string;
  platformId: string;
  mid: string;
  title: string;
  name: string;
  artist: string;
  album: string;
  duration: number | null;
  cover: string | null;
  resolvedId?: string;
  canPlay?: boolean;
  resolveState: 'idle' | 'resolving' | 'resolved' | 'failed';
  ext?: never;
  playable?: never;
}
export type SearchEntry = Song | CandidateRow;

/** 稳定的录制标识；瞬态候选/媒体句柄从不用于定义队列键。 */
export type TrackIdentity = import('./core').TrackIdentity;
export interface TrackSnapshot {
  title: string;
  artist: string;
  album: string;
  durationSeconds: number | null;
  cover: string | null;
}
export interface QueueEntry {
  key: string;
  track: TrackIdentity;
  metadata: TrackSnapshot;
}

/** 本地条目只携带稳定文件引用，绝不伪装为在线平台。 */
export interface LocalSong {
  kind: 'local';
  fileId: string;
  id: string;
  source: 'local';
  name: string;
  title: string;
  artist: string;
  album: string;
  cover: string | null;
  duration: number | null;
}
export type PlayableSong = SearchEntry | LocalSong;
export interface LocalQueueEntry {
  key: string;
  kind: 'local';
  fileId: string;
  metadata: TrackSnapshot;
}
export type PlayableQueueEntry = QueueEntry | LocalQueueEntry;
export const isLocalSong = (song: PlayableSong): song is LocalSong =>
  'kind' in song && song.kind === 'local';

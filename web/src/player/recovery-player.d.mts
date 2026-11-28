import type { TrackIdentity } from '../types/core';

type Session = { playbackId: string; streamUrl: string; identity: TrackIdentity; expiresInSeconds: number };

export class RecoveryPlayer {
  constructor(audio: HTMLAudioElement, options: {
    operations: {
      open(identity: TrackIdentity): Promise<Session>;
      renew(id: string): Promise<void>;
      close(id: string): Promise<void>;
      probe(url: string): Promise<Response>;
    };
    notify?(state: { phase: string; message: string; automaticUsed: boolean; hasSession: boolean }): void;
  });
  session: Session | null;
  identity: TrackIdentity | null;
  operation: unknown;
  phase: string;
  desiredPlaying: boolean;
  select(identity: TrackIdentity, startAt?: number): Promise<void>;
  stop(): Promise<void>;
  dispose(): Promise<void>;
  waitMedia(predicate: () => boolean, events: string[], signal: AbortSignal): Promise<void>;
  setPlaying(value: boolean): Promise<void>;
  renew(): Promise<void>;
  recover(automatic?: boolean): Promise<void>;
  seek(seconds: number): void;
}

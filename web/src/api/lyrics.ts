import type { TrackIdentity, LyricDocument } from '../types/core';
import { isDesktop } from '../platform/desktop';
import { requestJson } from './http';
import { invokeCore } from './transport';

export const getLyrics = (identity: TrackIdentity, signal?: AbortSignal) =>
  isDesktop
    ? invokeCore<LyricDocument>({ op: 'lyricsGet', payload: identity }, { signal, timeoutMs: 20_000 })
    : requestJson<LyricDocument>('/api/lyrics?' + new URLSearchParams({ ...identity }), { signal });

import type { LyricDocument, OpenResponse, TrackIdentity } from '../types/core';
import { desktopPlatform, isDesktop } from '../platform/desktop.ts';
import { ApiError } from './error.ts';
import { requestJson } from './http.ts';
import { invokeCore } from './transport.ts';

type Session = { playbackId: string; streamUrl: string };
type OnlineSession = Session & { identity: TrackIdentity; expiresInSeconds: number };
type LocalSession = Session & { cover?: string | null; lyrics?: LyricDocument | null };

export function closePlayback(playbackId: string): Promise<void> {
  if (isDesktop) {
    if (!/^[a-f0-9]{32}$/.test(playbackId)) return Promise.resolve();
    return invokeCore({ op: 'playbackClose', payload: { playbackId } });
  }
  if (!/^[A-Za-z0-9_-]+$/.test(playbackId)) return Promise.resolve();
  return requestJson(`/api/playback/${playbackId}/close`, { method: 'POST', keepalive: true });
}

async function validateSession(session: Session) {
  const { playbackId, streamUrl } = session ?? {};
  try {
    if (typeof playbackId !== 'string' || typeof streamUrl !== 'string') throw new Error();
    if (isDesktop) {
      const { mediaPort } = await desktopPlatform();
      if (!/^[a-f0-9]{32}$/.test(playbackId) ||
          streamUrl !== `http://127.0.0.1:${mediaPort}/api/playback/${playbackId}/stream`) throw new Error();
    } else {
      if (!/^[A-Za-z0-9_-]+$/.test(playbackId) ||
          streamUrl.split('?')[0] !== `/api/playback/${playbackId}/stream` ||
          streamUrl.includes('#')) throw new Error();
    }
  } catch {
    if (typeof playbackId === 'string') await closePlayback(playbackId).catch(() => {});
    throw new ApiError(502, '播放会话地址无效', 'invalid_response');
  }
}

export async function openLocalPlayback(id: string) {
  const session = await invokeCore<LocalSession>({ op: 'libraryOpen', payload: { id } });
  await validateSession(session);
  return session;
}

async function openPlayback(identity: TrackIdentity): Promise<OnlineSession> {
  let session: OnlineSession;
  if (isDesktop) {
    session = await invokeCore({ op: 'playbackOpen', payload: { identity } });
  } else {
    const open = await requestJson<OpenResponse>('/api/playback/open', {
      method: 'POST', body: JSON.stringify({ identity }), mutation: true,
    });
    session = { ...open, identity: open?.media?.identity };
  }
  await validateSession(session);
  if (!Number.isFinite(session.expiresInSeconds) || session.expiresInSeconds <= 0) {
    await closePlayback(session.playbackId).catch(() => {});
    throw new ApiError(502, '播放会话有效期无效', 'invalid_response');
  }
  return session;
}

async function renewPlayback(playbackId: string): Promise<void> {
  if (isDesktop) return invokeCore({ op: 'playbackRenew', payload: { playbackId } });
  return requestJson(`/api/playback/${playbackId}/renew`, { method: 'POST' });
}

export const playbackOperations = {
  open: openPlayback,
  renew: renewPlayback,
  close: closePlayback,
  probe: (url: string) => fetch(url, { method: 'HEAD', signal: AbortSignal.timeout(12000) }),
};

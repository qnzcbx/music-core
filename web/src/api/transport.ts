import { bridge } from '../platform/desktop.ts';
import { ApiError } from './error.ts';
import type { DownloadQuality, OutputMode, ProviderId, TrackIdentity } from '../types/core';

type Id = { id: string };
type Lease = { playbackId: string };
type Token = { token: string };
type DownloadInput = {
  identity: TrackIdentity;
  quality?: DownloadQuality;
  outputMode?: OutputMode;
  expectedSourceCodec?: 'flac' | null;
  saveAs?: boolean;
  title?: string | null;
  artist?: string | null;
  album?: string | null;
  cover?: string | null;
};

type DesktopPayloads = {
  providersList: null;
  searchPage: { providerId: ProviderId; query: string; limit: number; cursor: string | null };
  lyricsGet: TrackIdentity;
  paletteRelay: { url: string };
  cachedCover: { identity: TrackIdentity; cover?: string | null };
  queueCovers: { entries: ({ fileId: string } | { track: TrackIdentity })[] };
  cacheSettings: null;
  cacheOpen: null;
  cacheClear: { scope: 'cover' | 'lyrics' | 'all' };
  downloadOptions: DownloadInput;
  downloadCreate: DownloadInput;
  downloadsList: null;
  downloadCancel: Id;
  downloadRetry: Id;
  downloadDismiss: Id;
  downloadSettings: null;
  downloadNaming: { naming: string };
  downloadDirectory: { action: 'choose' | 'reset' | 'open' };
  libraryList: null;
  libraryImport: null;
  libraryChooseDirectory: null;
  libraryRefreshDirectory: Id;
  libraryRemoveDirectory: Id;
  libraryOpen: Id;
  libraryReveal: Id;
  libraryRemove: Id;
  recyclePrepare: Id & { pathHint?: string };
  recycleCancel: Token;
  recycleExecute: Token;
  playbackOpen: { identity: TrackIdentity };
  playbackRenew: Lease;
  playbackClose: Lease;
};

type CoreRequest = {
  [Op in keyof DesktopPayloads]: DesktopPayloads[Op] extends null
    ? { op: Op }
    : { op: Op; payload: DesktopPayloads[Op] };
}[keyof DesktopPayloads];

type RequestOptions =
  | { signal?: AbortSignal; timeoutMs?: number; mutation?: false }
  | { mutation: true; signal?: never; timeoutMs?: never };

export async function invokeCore<T>(request: CoreRequest, options: RequestOptions = {}): Promise<T> {
  const { signal, timeoutMs, mutation } = options;
  signal?.throwIfAborted();
  if (!bridge) throw new ApiError(503, '桌面宿主不可用', 'desktop_unavailable');

  // 只有纯查询可以取消等待。宿主已执行的工作仍会完成。
  const stopped = new AbortController();
  const abort = () => stopped.abort(signal?.reason);
  const timeout = timeoutMs === undefined ? undefined : setTimeout(() => {
    stopped.abort(new ApiError(504, '读取超时，请重试', 'request_timeout', true));
  }, timeoutMs);
  signal?.addEventListener('abort', abort, { once: true });
  try {
    const pending = bridge.core.invoke<T>('core_request', { request });
    if (!signal && timeout === undefined) return await pending;
    return await new Promise<T>((resolve, reject) => {
      const cancel = () => reject(stopped.signal.reason);
      stopped.signal.addEventListener('abort', cancel, { once: true });
      pending.then(resolve, reject).finally(() => stopped.signal.removeEventListener('abort', cancel));
      if (stopped.signal.aborted) cancel();
    });
  } catch (reason) {
    if (stopped.signal.aborted) throw stopped.signal.reason;
    const fault = reason as Partial<{ code: string; message: string; status: number; retryable: boolean }> | null;
    if (typeof fault?.status === 'number' && typeof fault.code === 'string' &&
        typeof fault.message === 'string' && typeof fault.retryable === 'boolean') {
      throw new ApiError(fault.status, fault.message, fault.code, fault.retryable);
    }
    if (mutation) throw new ApiError(503, '操作结果未确认，请刷新后检查。', 'outcome_unknown');
    throw new ApiError(503, '桌面请求失败，请重试', 'desktop_unavailable', true);
  } finally {
    signal?.removeEventListener('abort', abort);
    clearTimeout(timeout);
  }
}

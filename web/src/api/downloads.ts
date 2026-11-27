import type {
  DownloadQualityOption,
  DownloadRequest,
  DownloadTask,
  SavedDownloadFile,
  TrackIdentity,
} from '../types/core';
import { isDesktop } from '../platform/desktop';
import { requestJson } from './http';
import { invokeCore } from './transport';

export const supportedDownloadQualities = ['auto', 'standard', 'high', 'lossless'];
export type Choice<T> = { status: 'selected'; value: T } | { status: 'cancelled' };

export async function createDownload(body: DownloadRequest) {
  if (isDesktop) {
    const result = await invokeCore<Choice<DownloadTask>>(
      { op: 'downloadCreate', payload: body },
      { mutation: true },
    );
    return result.status === 'selected' ? result.value : null;
  }
  return requestJson<DownloadTask>('/api/downloads', {
    method: 'POST',
    body: JSON.stringify(body),
    mutation: true,
  });
}

export const listDownloads = (signal?: AbortSignal) =>
  requestJson<DownloadTask[]>('/api/downloads', { signal });
export const listDownloadFiles = (signal?: AbortSignal) =>
  requestJson<SavedDownloadFile[]>('/api/downloads/files', { signal });

export async function updateDownload(id: string, operation: 'cancel' | 'retry') {
  if (isDesktop) {
    if (operation === 'cancel')
      return invokeCore<DownloadTask>(
        { op: 'downloadCancel', payload: { id } },
        { mutation: true },
      );
    const result = await invokeCore<Choice<DownloadTask>>(
      { op: 'downloadRetry', payload: { id } },
      { mutation: true },
    );
    return result.status === 'selected' ? result.value : null;
  }
  return requestJson<DownloadTask>(`/api/downloads/${encodeURIComponent(id)}/${operation}`, {
    method: 'POST',
    mutation: true,
  });
}

export const localStreamUrl = (fileId: string) =>
  `/api/downloads/files/${encodeURIComponent(fileId)}/stream`;
export const removeDownloadFile = (fileId: string, deleteFile: boolean) =>
  requestJson<{ removed: boolean; fileDeleted: boolean }>(
    `/api/downloads/files/${encodeURIComponent(fileId)}/remove`,
    { method: 'POST', body: JSON.stringify({ deleteFile }), mutation: true },
  );

export function checkDownloadQuality(body: DownloadRequest, signal?: AbortSignal) {
  return isDesktop
    ? invokeCore<DownloadQualityOption>(
        { op: 'downloadOptions', payload: body },
        { signal, timeoutMs: 55_000 },
      )
    : requestJson<DownloadQualityOption>('/api/downloads/options', {
        timeoutMs: 55_000,
        method: 'POST',
        body: JSON.stringify(body),
        signal,
      });
}

export const pollDesktopDownloads = (signal?: AbortSignal) =>
  invokeCore<{ tasks: DownloadTask[]; saved: { id: string; identity: TrackIdentity }[] }>(
    { op: 'downloadsList' },
    { signal, timeoutMs: 20_000 },
  );

export const dismissDesktopDownload = (id: string) =>
  invokeCore<void>({ op: 'downloadDismiss', payload: { id } }, { mutation: true });

export type DownloadSettings = {
  mode?: 'local' | 'browser' | 'desktop';
  directory?: string;
  defaultDirectory?: string;
  usingDefaultDirectory?: boolean;
  naming: string;
  error: string | null;
  deploymentLocked: boolean;
  canManage: boolean;
};

export const getDownloadSettings = () =>
  isDesktop
    ? invokeCore<DownloadSettings>({ op: 'downloadSettings' }, { timeoutMs: 20_000 })
    : requestJson<DownloadSettings>('/api/downloads/settings');

export const saveDownloadNaming = (naming: string) =>
  isDesktop
    ? invokeCore<DownloadSettings>(
        { op: 'downloadNaming', payload: { naming } },
        { mutation: true },
      )
    : requestJson<{ naming: string }>('/api/downloads/settings', {
        method: 'PUT',
        body: JSON.stringify({ naming }),
        mutation: true,
      });

import { requestJson } from "./http";
import { isDesktop } from './transport';
export const desktopDownloads = isDesktop;
export const supportedDownloadQualities = ['auto', 'standard', 'high', 'lossless'];
export const revealDownload = (id: string) =>
  requestJson<null>(`/api/downloads/${encodeURIComponent(id)}/reveal`, { method: 'POST' });
import type { DownloadRequest, DownloadTask, SavedDownloadFile } from "../types/core";
export const createDownload = (body: DownloadRequest, signal?: AbortSignal) =>
  requestJson<DownloadTask | null>("/api/downloads", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
export const listDownloads = (signal?: AbortSignal) =>
  requestJson<DownloadTask[]>("/api/downloads", { signal });
export const listDownloadFiles = (signal?: AbortSignal) =>
  requestJson<SavedDownloadFile[]>("/api/downloads/files", { signal });
export const updateDownload = (id: string, operation: "cancel" | "retry", signal?: AbortSignal) =>
  requestJson<DownloadTask>(`/api/downloads/${encodeURIComponent(id)}/${operation}`, {
    method: "POST",
    signal,
  });

export const localStreamUrl = (fileId: string) =>
  `/api/downloads/files/${encodeURIComponent(fileId)}/stream`;
export const removeDownloadFile = (fileId: string, deleteFile: boolean) =>
  requestJson<{ removed: boolean; fileDeleted: boolean }>(
    `/api/downloads/files/${encodeURIComponent(fileId)}/remove`,
    { method: "POST", body: JSON.stringify({ deleteFile }) },
  );

export const checkDownloadQuality=(body:DownloadRequest,signal?:AbortSignal)=>requestJson<import('../types/core').DownloadQualityOption>('/api/downloads/options',{timeoutMs:55000,method:'POST',body:JSON.stringify(body),signal});

export const listDesktopSaved = (signal?: AbortSignal) =>
  requestJson<import('../types/core').DesktopSavedDownload[]>('/api/downloads/saved', { signal });
export const revealDesktopSaved = (id: string) =>
  requestJson<null>(`/api/downloads/saved/${encodeURIComponent(id)}/reveal`, { method: 'POST' });

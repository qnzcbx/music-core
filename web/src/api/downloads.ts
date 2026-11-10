import {requestJson} from './http';
import type {DownloadRequest,DownloadTask,SavedDownloadFile} from '../types/core';
export const createDownload=(body:DownloadRequest,signal?:AbortSignal)=>requestJson<DownloadTask>('/api/downloads',{method:'POST',body:JSON.stringify(body),signal});
export const listDownloads=(signal?:AbortSignal)=>requestJson<DownloadTask[]>('/api/downloads',{signal});
export const listDownloadFiles=(signal?:AbortSignal)=>requestJson<SavedDownloadFile[]>('/api/downloads/files',{signal});
export const updateDownload=(id:string,operation:'cancel'|'retry',signal?:AbortSignal)=>requestJson<DownloadTask>(`/api/downloads/${encodeURIComponent(id)}/${operation}`,{method:'POST',signal});

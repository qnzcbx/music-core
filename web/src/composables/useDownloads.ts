import { computed, onMounted, onScopeDispose, ref, shallowRef, watch } from 'vue';
import {
  createDownload,
  listDownloads,
  listDownloadFiles,
  listDesktopSaved,
  revealDesktopSaved,
  updateDownload,
  removeDownloadFile,
} from '../api/downloads';
import { requestJson, ApiError } from '../api/http';
import { desktopDownloads, revealDownload } from '../api/downloads';
import { downloadError } from '../utils/download-display';
import { trackIdentity, queueKey } from '../utils/player-queue';
import type { SearchEntry } from '../types/music';
import type {
  DownloadTask, SavedDownloadFile, DesktopSavedDownload, DownloadQuality, OutputMode,
} from '../types/core';

export const activeDownload = (task: DownloadTask) =>
  ['queued', 'resolving', 'downloading'].includes(task.status);
export function useDownloads() {
  const localMode = ref(false);
  const deliveries = ref<
    Record<string, { state: 'preparing' | 'handed' | 'ready' | 'failed'; text: string }>
  >({});
  const delivering = ref(new Set<string>());
  // 仅恢复已发起状态，刷新不重复交付。
  try {
    for (const id of JSON.parse(sessionStorage.getItem('download-handed') || '[]')) {
      if (typeof id === 'string' && /^[a-f0-9]{32}$/.test(id))
        deliveries.value[id] = { state: 'handed', text: '已发起下载' };
    }
  } catch {}
  function rememberHanded() {
    try {
      const ids = Object.keys(deliveries.value).filter(
        (id) => deliveries.value[id]?.state === 'handed',
      );
      sessionStorage.setItem('download-handed', JSON.stringify(ids.slice(-500)));
    } catch {}
  }
  function artifactUrl(task: DownloadTask) {
    return /^[a-f0-9]{32}$/.test(task.id) &&
      task.artifactUrl === `/api/downloads/${task.id}/artifact`
      ? task.artifactUrl
      : null;
  }
  async function deliver(task: DownloadTask, prepareExpired = false) {
    const url = artifactUrl(task);
    if (delivering.value.has(task.id) || pending.value.has(task.id)) return;
    if (!url) {
      if (prepareExpired) await prepareAgain(task);
      return;
    }
    delivering.value = new Set([...delivering.value, task.id]);
    try {
      const response = await fetch(url, { method: 'HEAD' });
      if (response.status === 410 && prepareExpired) {
        await prepareAgain(task);
        return;
      }
      if (!response.ok)
        throw new Error(
          response.status === 410 ? '成品已过期，请重新准备下载' : '无法交付，请重试',
        );
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = task.filename || '';
      anchor.hidden = true;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      deliveries.value[task.id] = {
        state: 'handed',
        text: '已发起下载',
      };
      rememberHanded();
      feedback.value = {
        key: task.id,
        text: task.sourcePreserved
          ? '文件压缩失败，已发起原文件下载'
          : `开始下载${task.title ? '：《' + task.title + '》' : ''}`,
        error: task.sourcePreserved === true,
      };
    } catch (reason) {
      deliveries.value[task.id] = {
        state: 'failed',
        text: reason instanceof Error ? reason.message : '浏览器交付失败，请重试',
      };
      feedback.value = { key: task.id, text: deliveries.value[task.id]!.text, error: true };
    } finally {
      delivering.value = new Set([...delivering.value].filter((id) => id !== task.id));
    }
  }
  const tasks = shallowRef<DownloadTask[]>([]),
    files = shallowRef<SavedDownloadFile[]>([]),
    saved = shallowRef<DesktopSavedDownload[]>([]),
    loading = ref(false),
    error = ref(''),
    fileError = ref('');
  const feedback = ref<{ key: string; text: string; error?: boolean; taskId?: string } | null>(
      null,
    ),
    pending = ref(new Set<string>()),
    covers = ref<Record<string, string | null>>({}),
    retried = ref<Record<string, string>>({});
  let revision = 0,
    disposed = false,
    timer: ReturnType<typeof setTimeout> | undefined,
    inflight: Promise<void> | undefined,
    again = false,
    wantFiles = false;
  const queries = new Set<AbortController>(),
    operations = new Map<string, Promise<DownloadTask | undefined>>();
  const downloadSong = shallowRef<SearchEntry | null>(null);
  function choose(song: SearchEntry) {
    trackIdentity(song);
    downloadSong.value = song;
  }
  function closeChoice() {
    downloadSong.value = null;
  }
  const active = computed(() => tasks.value.some(activeDownload));
  const message = (reason: unknown) =>
    reason instanceof TypeError
      ? '无法连接下载服务，请稍后重试'
      : reason instanceof Error
        ? reason.name === 'AbortError'
          ? '请求超时，请稍后重试'
          : reason.message
        : '下载操作失败';
  function arm() {
    clearTimeout(timer);
    if (!disposed && !document.hidden && active.value)
      timer = setTimeout(() => void refresh(false), error.value ? 5000 : 1500);
  }
  function upsert(task: DownloadTask) {
    const old = tasks.value.find((t) => t.id === task.id);
    if (old && old.updatedAt > task.updatedAt) return;
    tasks.value = [...tasks.value.filter((t) => t.id !== task.id), task];
  }
  function refresh(withFiles = true): Promise<void> {
    if (disposed) return Promise.resolve();
    if (withFiles) wantFiles = true;
    if (inflight) return inflight;
    clearTimeout(timer);
    loading.value = true;
    const token = revision,
      request = new AbortController();
    queries.add(request);
    inflight = (async () => {
      try {
        const data = await listDownloads(request.signal);
        if (disposed || token !== revision) return;
        const completed = data.some(
          (t) =>
            (t.status === 'completed' || t.sourcePreserved) &&
            tasks.value.find((old) => old.id === t.id)?.status !== 'completed',
        );
        tasks.value = data;
        error.value = '';
        if (desktopDownloads && (wantFiles || completed)) {
          wantFiles = false;
          try {
            const records = await listDesktopSaved(request.signal);
            if (!disposed && token === revision) {
              saved.value = records;
              fileError.value = '';
            }
          } catch (reason) {
            if (!disposed && token === revision) fileError.value = message(reason);
          }
        }
        if (!localMode.value && !desktopDownloads) wantFiles = false;
        if (localMode.value && (wantFiles || completed)) {
          wantFiles = false;
          try {
            const saved = await listDownloadFiles(request.signal);
            if (!disposed && token === revision) {
              files.value = saved;
              fileError.value = '';
            }
          } catch (reason) {
            if (!disposed && token === revision) fileError.value = message(reason);
          }
        }
      } catch (reason) {
        if (!disposed && token === revision) error.value = message(reason);
      } finally {
        queries.delete(request);
        inflight = undefined;
        loading.value = false;
        if ((again || (wantFiles && !error.value)) && !disposed) {
          again = false;
          void refresh();
        } else arm();
      }
    })();
    return inflight;
  }
  async function perform(key: string, action: () => Promise<DownloadTask | null>, notice: string) {
    const running = operations.get(key);
    if (running) return running;
    revision++;
    pending.value = new Set([...pending.value, key]);
    feedback.value = null;
    const work = (async () => {
      try {
        const task = await action();
        if (disposed || !task) return;
        if (task.deliveryMode === 'browser')
          deliveries.value[task.id] = { state: 'preparing', text: '正在准备下载' };
        upsert(task);
        feedback.value = {
          key,
          taskId: task.id,
          text: task.status === 'failed' ? '下载失败' : notice,
          error: task.status === 'failed',
        };
        if (task.status === 'failed')
          console.error('下载失败', { identity: task.identity, code: task.errorCode });
        return task;
      } catch (reason) {
        console.error('下载请求失败', reason);
        if (!disposed)
          feedback.value = {
            key,
            error: true,
            text:
              reason instanceof ApiError && reason.status === 404
                ? '任务不存在或已过期，请刷新'
                : reason instanceof ApiError && reason.status === 429
                  ? '下载任务过多，请稍后重试'
                  : message(reason),
          };
      } finally {
        operations.delete(key);
        const next = new Set(pending.value);
        next.delete(key);
        pending.value = next;
        revision++;
        if (inflight) again = true;
        else void refresh();
      }
    })();
    operations.set(key, work);
    return work;
  }
  async function create(
    song: SearchEntry,
    quality: DownloadQuality = 'auto',
    outputMode: OutputMode = 'original',
    expectedSourceCodec: 'flac' | null = null,
    saveAs = false,
  ) {
    const identity = trackIdentity(song),
      key = queueKey(identity);
    const existing = [...tasks.value]
      .reverse()
      .find(
        (task) =>
          queueKey(task.identity) === key &&
          (task.quality ?? 'auto') === quality &&
          (task.outputMode ?? 'original') === outputMode &&
          (task.status !== 'completed' || files.value.some((f) => f.fileId === task.fileId)),
      );
    if (existing) {
      feedback.value = {
        key,
        text:
          existing.status === 'completed'
            ? '该版本已有完成记录，可在下载页查看'
            : activeDownload(existing)
              ? '该歌曲已在下载任务中'
              : '该版本已有任务，可在下载页重试',
      };
      return existing;
    }
    covers.value[key] = song.cover ?? null;
    return perform(
      key,
      () =>
        createDownload({
          identity,
          quality,
          outputMode,
          expectedSourceCodec,
          ...(desktopDownloads ? { saveAs } : {}),
          title: song.title || song.name,
          artist: song.artist,
          album: song.album,
          cover: song.cover,
        }),
      '已加入下载任务',
    );
  }
  async function operate(task: DownloadTask, operation: 'cancel' | 'retry') {
    if (operation === 'retry' && retried.value[task.id]) return;
    const result = await perform(
      task.id,
      () => updateDownload(task.id, operation),
      operation === 'retry' ? '已发起重试' : '已更新任务状态',
    );
    if (result && operation === 'retry') retried.value = { ...retried.value, [task.id]: result.id };
    return result;
  }
  function prepareAgain(task: DownloadTask) {
    return perform(
      task.id,
      () =>
        createDownload({
          identity: task.identity,
          title: task.title,
          artist: task.artist,
          album: task.album,
          cover: task.cover,
          quality: task.quality,
          outputMode: task.outputMode,
          expectedSourceCodec: task.expectedSourceCodec,
        }),
      '已发起重试',
    );
  }
  async function downloadAgain(task: DownloadTask) {
    if (pending.value.has(task.id) || delivering.value.has(task.id)) return;
    if (task.artifactUrl && !task.sourcePreserved) await deliver(task, true);
    else await prepareAgain(task);
  }
  async function removeFile(file: SavedDownloadFile, deleteFile: boolean) {
    if (pending.value.has(file.fileId)) return false;
    revision++;
    pending.value = new Set([...pending.value, file.fileId]);
    feedback.value = null;
    try {
      await removeDownloadFile(file.fileId, deleteFile);
      files.value = files.value.filter((f) => f.fileId !== file.fileId);
      feedback.value = {
        key: file.fileId,
        text: deleteFile ? '已删除本地音频文件' : '已移除下载记录，文件仍保留',
      };
      return true;
    } catch (reason) {
      fileError.value = message(reason);
      return false;
    } finally {
      const next = new Set(pending.value);
      next.delete(file.fileId);
      pending.value = next;
      revision++;
      if (inflight) again = true;
      else void refresh();
    }
  }
  watch(tasks, (rows) => {
    for (const task of rows) {
      if (task.deliveryMode !== 'browser' || deliveries.value[task.id]?.state !== 'preparing')
        continue;
      if (task.status === 'completed') void deliver(task);
      else if (task.status === 'failed' && task.sourcePreserved && task.artifactUrl)
        void deliver(task);
      else if (task.status === 'failed' || task.status === 'cancelled')
        deliveries.value[task.id] = {
          state: 'failed',
          text: task.sourcePreserved
            ? '转换失败，可手动保存有效 FLAC'
            : task.status === 'cancelled'
              ? '已取消'
              : downloadError(task.errorCode),
        };
    }
  });
  const visible = () => {
    if (document.hidden) clearTimeout(timer);
    else void refresh();
  };
  onMounted(() => {
    void requestJson<{ mode?: string }>('/api/downloads/settings')
      .then((value) => {
        localMode.value = value.mode === 'local';
      })
      .catch(() => {})
      .finally(() => void refresh());
    document.addEventListener('visibilitychange', visible);
  });
  onScopeDispose(() => {
    disposed = true;
    clearTimeout(timer);
    for (const request of queries) request.abort();
    document.removeEventListener('visibilitychange', visible);
  });
  return {
    desktopMode: desktopDownloads,
    reveal: revealDownload,
    localMode,
    deliveries,
    deliver,
    delivering,
    downloadAgain,
    artifactUrl,
    downloadSong,
    choose,
    closeChoice,
    tasks,
    files,
    saved,
    revealSaved: revealDesktopSaved,
    loading,
    error,
    fileError,
    feedback,
    pending,
    covers,
    retried,
    active,
    create,
    operate,
    refresh,
    removeFile,
  };
}

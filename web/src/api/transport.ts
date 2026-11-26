type DesktopWindow = Window & {
  __TAURI__?: { core: { invoke<T>(command: string, args: Record<string, unknown>): Promise<T> } };
};

export const isDesktop = typeof window !== 'undefined' && !!(window as DesktopWindow).__TAURI__;
const mediaUrls = new Set<string>();

export function isPlaybackUrl(url: string): boolean {
  return /^\/api\/playback\/[A-Za-z0-9_-]+\/stream(?:\?[^#]*)?$/.test(url) ||
    (isDesktop && mediaUrls.has(url));
}

/** 桌面轻量请求走 IPC，音频始终由 HTMLAudioElement 流式读取。 */
export const apiFetch: typeof fetch = async (input, init) => {
  if (!isDesktop) return fetch(input, init);
  const path = String(input);
  if (mediaUrls.has(path)) return fetch(path, init);
  if (init?.signal?.aborted) throw new DOMException('请求已取消', 'AbortError');
  let body = typeof init?.body === 'string' ? JSON.parse(init.body) : null;
  let commandPath=path;
  if(path.startsWith('/api/lyrics?')) {
    const params=new URLSearchParams(path.slice(path.indexOf('?')+1));
    body={providerId:params.get('providerId'),platformId:params.get('platformId')};
    commandPath='/api/lyrics';
  }
  try {
    const data = await (window as DesktopWindow).__TAURI__!.core.invoke<Record<string, unknown> | null>(
      'desktop_request', { path:commandPath, body },
    );
    if ((path === '/api/playback/open' || path === '/api/local-library/open') && typeof data?.streamUrl === 'string') {
      const url = new URL(data.streamUrl);
      if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port ||
          !/^\/api\/playback\/[a-f0-9]{32}\/stream$/.test(url.pathname)) {
        throw new Error('桌面媒体会话地址无效');
      }
      mediaUrls.add(data.streamUrl);
    }
    if (path.endsWith('/close')) {
      const id = path.split('/')[3];
      for (const url of mediaUrls) if (new URL(url).pathname.includes(`/${id}/`)) mediaUrls.delete(url);
    }
    return data === null ? new Response(null, { status: 204 }) : Response.json(data);
  } catch (error) {
    const code = String(error);
    const downloadMessages: Record<string, string> = {
      download_history_unavailable: '无法读取或保存下载设置与记录，请检查应用配置目录',
      download_history_invalid: '下载记录文件无法读取，原文件未改动',
      local_directory_unavailable: '目录暂不可用，已有记录已保留',
      local_library_unavailable: '无法读取或保存本地歌曲记录',
      local_recycle_unavailable: '此位置无法使用系统回收站。可取消勾选，仅从曲库移除。',
      local_recycle_identity_unavailable: '无法确认文件身份，请重新导入或刷新来源文件夹。',
      local_recycle_unsafe_path: '此文件位置无法安全回收。',
      local_recycle_changed: '文件或曲库记录已变化，请刷新列表后重新确认。',
      local_recycle_plan_invalid: '删除确认已过期或失效，请重新打开删除窗口。',
      local_recycle_cancelled: '系统已取消回收，曲库记录已保留。',
      local_recycle_failed: '系统回收失败，请检查文件是否被占用或回收站是否可用。',
      local_recycle_uncertain: '系统没有确认回收结果。请检查原文件和回收站，曲库记录已保留。',
      local_unsupported: '请选择可播放的 MP3 或 FLAC 文件',
      saved_file_missing: '文件已移动或删除，记录中的原位置已不存在',
      file_exists: '目标文件已存在，请选择其他名称或位置',
      file_io_error: '文件保存失败，请检查所选位置',
      access_denied: '未确认该曲目允许下载，请重新搜索或选择其他曲目',
      capability_unsupported: '当前来源暂不支持所选品质或格式',
      media_unavailable: '所选品质不可用',
      upstream_timeout: '下载准备超时，请重试',
      upstream_failure: '下载来源暂时无法连接，请重试',
    };
    const message = (path.startsWith('/api/downloads') || path.startsWith('/api/local-library')) ? (downloadMessages[code] ?? code) : code;
    return Response.json({ error: { code: code.startsWith('local_recycle_') ? code : 'DESKTOP_UNAVAILABLE', message } }, { status: 503 });
  }
};

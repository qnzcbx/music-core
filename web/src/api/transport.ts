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
    if (path === '/api/playback/open' && typeof data?.streamUrl === 'string') {
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
    return Response.json({ error: { code: 'DESKTOP_UNAVAILABLE', message: String(error) } }, { status: 503 });
  }
};

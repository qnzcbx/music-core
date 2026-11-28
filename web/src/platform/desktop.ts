type Bridge = {
  core: { invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> };
  event: { listen<T>(name: string, handler: (event: { payload: T }) => void): Promise<() => void> };
};

export const bridge = typeof window === 'undefined'
  ? undefined
  : (window as Window & { __TAURI__?: Bridge }).__TAURI__;
export const isDesktop = !!bridge;

export type DesktopPlatform = {
  window: string;
  mediaPort: number;
  tray: boolean;
  desktopLyrics: boolean;
  recycle: boolean;
  mediaCache: boolean;
  hidden: boolean;
  lyricsVisible: boolean;
};

let platform: Promise<DesktopPlatform> | undefined;
export function desktopPlatform() {
  if (!bridge) return Promise.reject(new Error('桌面宿主不可用'));
  return platform ??= bridge.core.invoke<DesktopPlatform>('desktop_platform').catch((error) => {
    platform = undefined;
    throw error;
  });
}

export function readDesktopPlatform() {
  return bridge?.core.invoke<DesktopPlatform>('desktop_platform');
}

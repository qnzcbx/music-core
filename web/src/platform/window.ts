import { computed, onScopeDispose, readonly, ref, shallowRef } from 'vue';
import { bridge, desktopPlatform, readDesktopPlatform, type DesktopPlatform } from './desktop.ts';

const capabilities = shallowRef<DesktopPlatform>();
export const desktopCapabilities = readonly(capabilities);

const documentHidden = ref(typeof document !== 'undefined' && document.hidden);
const windowHidden = ref(false);
export const pageVisible = computed(() => !documentHidden.value && !windowHidden.value);

export function listenDesktop<T>(name: string, handler: (payload: T) => void) {
  let disposed = false;
  let unlisten: (() => void) | undefined;
  onScopeDispose(() => {
    disposed = true;
    unlisten?.();
  });
  if (!bridge) return Promise.resolve(false);
  return bridge.event.listen<T>(name, ({ payload }) => {
    if (!disposed) handler(payload);
  }).then((stop) => {
    if (disposed) stop();
    else unlisten = stop;
    return !disposed;
  }).catch((error) => {
    if (!disposed) console.error('桌面事件注册失败', name, error);
    return false;
  });
}

export function trackPageVisibility() {
  const updateDocument = () => { documentHidden.value = document.hidden; };
  updateDocument();
  document.addEventListener('visibilitychange', updateDocument);
  let disposed = false;
  let revision = 0;
  onScopeDispose(() => {
    disposed = true;
    document.removeEventListener('visibilitychange', updateDocument);
  });
  if (!bridge) return;
  void desktopPlatform().then((platform) => {
    if (!disposed) capabilities.value = platform;
  }).catch(console.error);
  void listenDesktop<boolean>('desktop-main-hidden', (hidden) => {
    revision++;
    windowHidden.value = hidden;
  }).then(async (registered) => {
    if (!registered || disposed) return;
    const request = revision;
    const state = await readDesktopPlatform();
    if (state && !disposed && request === revision) windowHidden.value = state.hidden;
  }).catch(console.error);
}

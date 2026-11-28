import test from 'node:test';
import assert from 'node:assert/strict';
import { effectScope } from 'vue';

test('统一可见状态处理原生初始值、后续事件及异步监听注销', async () => {
  const listeners = new Map();
  const registered = new Map();
  const stopped = [];
  let hostSnapshot;
  let lateUnlisten;
  const document = new EventTarget();
  document.hidden = false;
  globalThis.document = document;
  globalThis.window = {
    __TAURI__: {
      core: { async invoke() {
        const pending = new Promise(resolve => { hostSnapshot = resolve; });
        registered.set('platform', (registered.get('platform') ?? 0) + 1);
        if (registered.get('platform') === 1) return { tray: true };
        return pending;
      } },
      event: { async listen(name, handler) {
        registered.set(name, (registered.get(name) ?? 0) + 1);
        listeners.set(name, handler);
        if (name === 'late') return new Promise(resolve => { lateUnlisten = resolve; });
        return () => { stopped.push(name); listeners.delete(name); };
      } },
    },
  };
  const scope = effectScope();
  try {
    const { pageVisible, trackPageVisibility, listenDesktop } = await import('../src/platform/window.ts');
    scope.run(() => {
      trackPageVisibility();
      void listenDesktop('late', () => { throw new Error('卸载后不应处理事件'); });
    });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(registered.get('desktop-main-hidden'), 1);
    listeners.get('desktop-main-hidden')({ payload: true });
    hostSnapshot({ hidden: false });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(pageVisible.value, false, '晚到初始值不能覆盖已收到的原生隐藏事件');
    listeners.get('desktop-main-hidden')({ payload: false });
    assert.equal(pageVisible.value, true);
    document.hidden = true;
    document.dispatchEvent(new Event('visibilitychange'));
    assert.equal(pageVisible.value, false);
    scope.stop();
    listeners.get('late')({ payload: true });
    lateUnlisten(() => { stopped.push('late'); });
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(stopped, ['desktop-main-hidden', 'late']);
  } finally {
    scope.stop();
    delete globalThis.document;
    delete globalThis.window;
  }
});

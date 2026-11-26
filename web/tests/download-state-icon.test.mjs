import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { parse, compileScript } from 'vue/compiler-sfc';
import * as vue from 'vue';
import ts from 'typescript';
import { queueKey } from '../src/utils/player-queue.ts';

// 编译真实组件脚本，只替换依赖注入和无关图标，不复制被测的状态判定。
const source = readFileSync(new URL('../src/components/DownloadStateIcon.vue', import.meta.url), 'utf8');
const { descriptor } = parse(source);
const compiled = compileScript(descriptor, { id: 'download-state-icon-test' });
const code = ts.transpileModule(compiled.content, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const identity = { providerId: 'qq', platformId: '003JvsTd2XI0D9' };
const task = (deliveryMode, status = 'completed', fields = {}) => ({
  id: 'download-fixture', identity, deliveryMode, status, ...fields,
});

function icon(rows, files = [], delivering = []) {
  const downloads = {
    tasks: vue.ref(rows), files: vue.ref(files), saved: vue.ref([]), desktopMode: false,
    delivering: vue.ref(new Set(delivering)), localMode: vue.ref(false),
  };
  downloads.savedKeys = vue.computed(() => new Set(downloads.saved.value.map((row) => queueKey(row.identity))));
  const exports = {};
  runInNewContext(code, {
    exports,
    require(name) {
      if (name === 'vue') return vue;
      if (name.includes('useCoreClient')) return { useCoreClient: () => ({ downloads }) };
      if (name.includes('player-queue')) return { queueKey };
      if (name.startsWith('~icons/')) return { default: {} };
      throw new Error(`Unexpected component dependency: ${name}`);
    },
  });
  const props = vue.reactive({ identity });
  const bindings = exports.default.setup(props, { expose() {} });
  return {
    downloads, props,
    state: () => bindings.state.value,
    label: () => bindings.label?.value ?? bindings.labels[bindings.state.value],
  };
}

test('桌面完成任务不能独自标记歌曲已下载', () => {
  const view = icon([task('desktop')]);
  view.downloads.desktopMode = true;
  assert.equal(view.state(), 'none');
  assert.equal(view.label(), '下载');
});

test('桌面按成品更新图标，删除最后一份才恢复下载', () => {
  const view = icon([task('desktop', 'resolving')]);
  view.downloads.desktopMode = true;
  assert.equal(view.state(), 'resolving');
  for (const phase of ['downloading', 'transcoding', 'verifying', 'output_verifying', 'publishing']) {
    view.downloads.tasks.value = [task('desktop', 'downloading', { phase })];
    assert.notEqual(view.state(), 'completed');
  }
  view.downloads.tasks.value = [];
  view.downloads.saved.value = [{ id: 'mp3', identity }, { id: 'flac', identity }];
  assert.equal(view.state(), 'completed');
  assert.equal(view.label(), '已下载');
  view.downloads.saved.value = [{ id: 'flac', identity }];
  assert.equal(view.state(), 'completed');
  view.downloads.saved.value = [];
  assert.equal(view.state(), 'none');
});

test('browser 交付中保持等待，交付结束恢复下载按钮，不标已下载', () => {
  const view = icon([task('browser')], [], ['download-fixture']);
  assert.equal(view.state(), 'downloading');
  view.downloads.delivering.value = new Set();
  assert.equal(view.state(), 'none');
  assert.equal(view.label(), '下载');
  view.downloads.files.value = [{ fileId: 'present' }];
  view.downloads.tasks.value = [task('browser', 'completed', { fileId: 'present' })];
  assert.equal(view.state(), 'none');
});

test('library 与旧任务仍以 fileId/files 确认完成', () => {
  for (const deliveryMode of ['library', undefined]) {
    const view = icon([task(deliveryMode)]);
    assert.equal(view.state(), 'unconfirmed');
    view.downloads.tasks.value = [task(deliveryMode, 'completed', { fileId: 'saved' })];
    assert.equal(view.state(), 'unconfirmed');
    view.downloads.files.value = [{ fileId: 'other' }];
    assert.equal(view.state(), 'unconfirmed');
    view.downloads.files.value = [{ fileId: 'saved' }];
    assert.equal(view.state(), 'completed');
    assert.equal(view.label(), '下载完成，文件存在');
  }
});

test('同 ID 不同来源不会继承已下载，失败任务不阻止下载', () => {
  const view = icon([task('desktop', 'failed')]);
  view.downloads.desktopMode = true;
  view.downloads.saved.value = [{ id: 'saved-record', identity }];
  view.props.identity = { providerId: 'qq', platformId: 'another-song' };
  assert.equal(view.state(), 'none');
  view.props.identity = { providerId: 'netease', platformId: identity.platformId };
  assert.equal(view.state(), 'none');
  view.props.identity = identity;
  view.downloads.saved.value = [];
  assert.equal(view.state(), 'none');
});

test('桌面重启后按成品记录显示已下载，不需要恢复旧任务或音乐库', () => {
  const view = icon([]);
  view.downloads.desktopMode = true;
  view.downloads.saved.value = [{ id: 'saved-record', identity, path: 'D:/outside/song.mp3' }];
  assert.equal(view.state(), 'completed');
  assert.equal(view.label(), '已下载');
});

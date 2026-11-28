<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { ApiError, requestJson } from '../api/http';
import {
  getDownloadSettings,
  saveDownloadNaming,
  type DownloadSettings as Settings,
  type Choice,
} from '../api/downloads';
import { invokeCore } from '../api/transport';
import { desktopCapabilities } from '../platform/window';

const settings = ref<Settings>();
const error = ref('');
const saving = ref(false);
const dialog = ref<HTMLDialogElement>();
const location = ref('music');
const customPath = ref('');
const migrate = ref(false);
const preview = ref<{ source: string; sources: string[]; target: string; count: number }>();
const result = ref('');
const directoryError = ref('');
const cacheDirectory = ref('');
const cacheBusy = ref(false);
const cacheFeedback = ref('');
const cacheActions = [
  { value: 'cover', label: '清理封面缓存' },
  { value: 'lyrics', label: '清理歌词缓存' },
  { value: 'all', label: '全部清理' },
] as const;

async function operateCache(action: 'open' | (typeof cacheActions)[number]['value']) {
  if (cacheBusy.value) return;
  cacheBusy.value = true;
  cacheFeedback.value = '';
  try {
    if (action === 'open') {
      await invokeCore({ op: 'cacheOpen' }, { mutation: true });
    } else {
      await invokeCore({ op: 'cacheClear', payload: { scope: action } }, { mutation: true });
      cacheFeedback.value = '已清理所选缓存，下载歌曲的离线资源已保留。';
    }
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'outcome_unknown') {
      cacheFeedback.value = reason.message;
      return;
    }
    cacheFeedback.value = action === 'open' ? '无法打开缓存文件夹。' : '缓存清理失败，请重试。';
  } finally {
    cacheBusy.value = false;
  }
}
async function load() {
  try {
    settings.value = await getDownloadSettings();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取下载设置';
  }
}
watch(
  () => desktopCapabilities.value?.mediaCache,
  async (available) => {
    if (!available) return;
    try {
      const cache = await invokeCore<{ directory: string }>(
        { op: 'cacheSettings' },
        { timeoutMs: 20_000 },
      );
      cacheDirectory.value = cache.directory;
    } catch {
      cacheFeedback.value = '缓存目录暂不可用。';
    }
  },
  { immediate: true },
);

async function authorize() {
  try {
    sessionStorage.removeItem('library-admin');
  } catch {
    /* 清理旧入口的会话残留不影响新的 HttpOnly 会话。 */
  }
  const ticket = new URLSearchParams(window.location.hash.slice(1)).get('local-launch');
  if (ticket) {
    history.replaceState(history.state, '', window.location.pathname + window.location.search);
    try {
      await requestJson('/api/downloads/settings/local-session', {
        method: 'POST',
        body: JSON.stringify({ ticket }),
      });
    } catch {
      error.value = '本机启动会话已失效，请从本机入口重新打开客户端';
    }
  }
  await load();
}
onMounted(() => {
  void authorize();
  window.addEventListener('hashchange', authorize);
});
onUnmounted(() => window.removeEventListener('hashchange', authorize));
function openDirectory() {
  preview.value = undefined;
  directoryError.value = '';
  migrate.value = false;
  dialog.value?.showModal();
}
function body() {
  return JSON.stringify({
    location: location.value,
    path: customPath.value,
    migrate: migrate.value,
  });
}
async function checkDirectory() {
  saving.value = true;
  directoryError.value = '';
  try {
    preview.value = await requestJson('/api/downloads/settings/directory/preview', {
      method: 'POST',
      body: body(),
    });
  } catch (reason) {
    directoryError.value = reason instanceof Error ? reason.message : '无法使用此目录';
  } finally {
    saving.value = false;
  }
}
async function saveDirectory() {
  saving.value = true;
  directoryError.value = '';
  try {
    const response = await requestJson<{
      results: { file: string; status: string; error?: string }[];
    }>('/api/downloads/settings/directory', {
      method: 'POST',
      body: body(),
      timeoutMs: 1800000,
      mutation: true,
    });
    const failed = response.results.filter((row) => row.status === 'failed');
    result.value = failed.length
      ? `目录已更新；部分迁移未完成：${failed.map((row) => row.file + '：' + row.error).join('；')}。已确认的副本或源文件仍保留。`
      : `保存目录已更新${migrate.value ? `，迁移完成 ${response.results.length} 个文件` : ''}`;
    await load();
    dialog.value?.close();
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'outcome_unknown') await load();
    directoryError.value = reason instanceof Error ? reason.message : '目录更改失败';
  } finally {
    saving.value = false;
  }
}
async function desktopDirectory(action: 'choose' | 'reset' | 'open') {
  if (saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    const result = await invokeCore<Choice<Settings>>(
      { op: 'downloadDirectory', payload: { action } },
      { mutation: true },
    );
    if (result.status === 'selected') settings.value = result.value;
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'outcome_unknown') await load();
    error.value = reason instanceof Error ? reason.message : '目录操作失败';
  } finally {
    saving.value = false;
  }
}
async function change(naming: string) {
  if (!settings.value || saving.value || settings.value.naming === naming) return;
  const previous = settings.value.naming;
  settings.value.naming = naming;
  saving.value = true;
  error.value = '';
  try {
    await saveDownloadNaming(naming);
  } catch (reason) {
    if (settings.value) settings.value.naming = previous;
    if (reason instanceof ApiError && reason.code === 'outcome_unknown') await load();
    error.value = reason instanceof Error ? reason.message : '保存命名格式失败，请重试';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="download-settings">
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <template v-if="settings">
      <template v-if="settings.mode === 'local'">
        <h3>音乐库保存目录</h3>
        <div class="directory-row">
          <code>{{ settings.directory }}</code>
          <button
            type="button"
            :disabled="settings.deploymentLocked || !settings.canManage || saving"
            @click="openDirectory"
          >
            更改目录
          </button>
        </div>
        <p v-if="settings.deploymentLocked">由部署配置管理</p>
        <p v-if="!settings.canManage && !settings.deploymentLocked">
          当前访问为只读。请从本机“打开音乐客户端”入口打开应用以管理目录。
        </p>
        <p
          v-if="result"
          role="status"
        >
          {{ result }}
        </p>
        <p
          v-if="settings.error"
          role="alert"
        >
          {{ settings.error }}
        </p>
      </template>
      <template v-else-if="settings.mode === 'desktop'">
        <section
          class="desktop-directory download-directory"
          aria-labelledby="download-directory-heading"
        >
          <h3 id="download-directory-heading">下载目录</h3>
          <div class="desktop-directory-fields">
            <p>下载的歌曲默认保存到此文件夹。</p>
            <div class="desktop-directory-actions">
              <input
                class="path-input"
                aria-label="默认下载目录"
                :value="settings.directory"
                readonly
              />
              <button
                type="button"
                :disabled="saving"
                @click="desktopDirectory('choose')"
              >
                更改目录
              </button>
              <button
                type="button"
                :disabled="saving"
                @click="desktopDirectory('open')"
              >
                打开文件夹
              </button>
              <button
                type="button"
                :disabled="saving || settings.usingDefaultDirectory"
                @click="desktopDirectory('reset')"
              >
                恢复默认
              </button>
            </div>
          </div>
        </section>
      </template>
      <p v-else>下载位置由浏览器管理</p>
      <fieldset
        :class="{ 'desktop-naming': settings.mode === 'desktop' }"
        :disabled="saving || (settings.mode === 'local' && !settings.canManage)"
      >
        <legend>文件命名格式</legend>
        <label
          v-for="choice in [
            { value: 'title', label: '歌曲名' },
            { value: 'artist_title', label: '歌手 - 歌曲名' },
            { value: 'title_artist', label: '歌曲名 - 歌手' },
          ]"
          :key="choice.value"
        >
          <input
            type="radio"
            name="download-naming"
            :value="choice.value"
            :checked="settings.naming === choice.value"
            @change="change(choice.value)"
          />
          {{ choice.label }}
        </label>
      </fieldset>
      <template v-if="settings.mode === 'desktop'">
        <section
          class="desktop-directory cache-row"
          aria-labelledby="cache-directory-heading"
        >
          <h3 id="cache-directory-heading">歌曲缓存设置</h3>
          <div class="desktop-directory-fields">
            <p>封面和歌词缓存在此文件夹。</p>
            <div class="desktop-directory-actions">
              <input
                class="path-input"
                aria-label="歌曲缓存目录"
                :value="cacheDirectory"
                readonly
              />
              <button
                type="button"
                :disabled="cacheBusy || !cacheDirectory"
                @click="operateCache('open')"
              >
                打开文件夹
              </button>
            </div>
          </div>
        </section>
        <section
          class="desktop-directory cache-row cache-usage"
          aria-labelledby="cache-usage-heading"
        >
          <h3 id="cache-usage-heading">缓存占用设置</h3>
          <div class="desktop-directory-fields">
            <div class="desktop-directory-actions">
              <button
                v-for="action in cacheActions"
                :key="action.value"
                type="button"
                :disabled="cacheBusy || !cacheDirectory"
                @click="operateCache(action.value)"
              >
                {{ action.label }}
              </button>
            </div>
            <p>仅清理普通缓存，已下载歌曲的离线封面和歌词会保留。</p>
            <p
              v-if="cacheFeedback"
              role="status"
            >
              {{ cacheFeedback }}
            </p>
          </div>
        </section>
      </template>
      <dialog
        ref="dialog"
        class="directory-dialog"
        @cancel="saving && $event.preventDefault()"
      >
        <h3>更改音乐库保存目录</h3>
        <p>选择后端机器上的目录，新任务立即生效；已创建的任务继续使用原目录。</p>
        <template v-if="settings.canManage">
          <template v-if="!preview">
            <fieldset :disabled="saving">
              <legend>保存位置</legend>
              <label
                v-for="option in [
                  { id: 'music', name: '音乐' },
                  { id: 'downloads', name: '下载' },
                  { id: 'custom', name: '自定义位置' },
                ]"
                :key="option.id"
              >
                <input
                  v-model="location"
                  type="radio"
                  name="library-location"
                  :value="option.id"
                />{{ option.name }}
              </label>
            </fieldset>
            <label
              v-if="location === 'custom'"
              class="path-label"
            >
              绝对目录路径
              <input
                v-model="customPath"
                class="path-input"
                type="text"
                :disabled="saving"
                placeholder="粘贴后端机器上的目录路径"
              />
            </label>
            <label class="migration-choice">
              <input
                v-model="migrate"
                type="checkbox"
                :disabled="saving"
              />同时迁移旧下载
            </label>
            <p v-if="migrate">
              迁移只处理有项目下载发布记录的文件；个人音乐及无法确认来源的旧文件不会搬动。
            </p>
            <p v-else>仅更改保存目录，不移动旧文件。</p>
          </template>
          <template v-else>
            <p>
              当前位置：<code
                v-for="source in preview.sources"
                :key="source"
                >{{ source }}</code
              >
            </p>
            <p>
              目标位置：<code>{{ preview.target }}</code>
            </p>
            <p>
              {{
                migrate
                  ? `将迁移 ${preview.count} 个已确认的项目下载文件`
                  : '仅更改保存目录，不移动文件'
              }}
            </p>
          </template>
          <p
            v-if="directoryError"
            role="alert"
          >
            {{ directoryError }}
          </p>
          <div class="dialog-actions">
            <button
              :disabled="saving"
              @click="preview ? (preview = undefined) : dialog?.close()"
            >
              {{ preview ? '返回' : '取消' }}
            </button>
            <button
              v-if="!preview"
              :disabled="saving"
              @click="checkDirectory"
            >
              检查目录
            </button>
            <button
              v-else
              :disabled="saving"
              @click="saveDirectory"
            >
              {{ saving ? '正在处理…' : '确认更改' }}
            </button>
          </div>
        </template>
      </dialog>
    </template>
  </div>
</template>

<style scoped>
code {
  display: block;
  overflow-wrap: anywhere;
  font-size: 13px;
}
h3 {
  font-size: 13px;
  font-weight: 500;
  margin: 0 0 12px;
}
p {
  font-size: 12px;
  line-height: 1.9;
  color: var(--app-text-muted);
}
fieldset {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  border: 0;
  padding: 0;
  margin: 22px 0 0;
}
legend {
  padding: 0;
  margin-bottom: 12px;
  font-size: 13px;
  font-weight: 500;
}
label {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  min-height: 36px;
  padding: 4px 12px;
  border: 1px solid var(--app-border-soft);
  border-radius: 8px;
  background: var(--app-surface-raised);
  cursor: pointer;
}
label:has(input:checked) {
  background: var(--app-selected);
  border-color: var(--app-border-strong);
}
input {
  accent-color: var(--app-accent);
}
fieldset:disabled label {
  cursor: wait;
}
[role='alert'] {
  color: var(--app-danger);
}
</style>

<style scoped>
.directory-dialog {
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100dvh - 40px);
  overflow: auto;
  box-sizing: border-box;
  padding: 24px;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: var(--app-surface-raised);
  color: var(--app-text);
}
.directory-dialog::backdrop {
  background: #0006;
}
button {
  padding: 8px 14px;
  border: 1px solid var(--app-border);
  border-radius: 7px;
  background: var(--app-surface);
  color: var(--app-text);
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
.path-label {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  margin-top: 16px;
}
.path-input {
  min-width: 0;
  width: 100%;
  padding: 8px;
  box-sizing: border-box;
  background: var(--app-surface);
  color: var(--app-text);
  border: 1px solid var(--app-border);
  border-radius: 5px;
}
.migration-choice {
  margin-top: 16px;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
</style>

<style scoped>
.directory-row {
  display: flex;
  align-items: center;
  gap: 16px;
}
.directory-row code {
  flex: 1;
  min-width: 0;
}
.directory-row button {
  flex-shrink: 0;
}
</style>

<style scoped>
.desktop-directory {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: baseline;
  gap: 16px;
  padding: 16px 0;
  border-block: 1px solid var(--app-border-soft);
}
.desktop-naming {
  margin-bottom: 16px;
}
.desktop-directory.download-directory {
  border-block-start: 0;
}
.desktop-directory.cache-row {
  border-bottom: 0;
}
.desktop-directory.cache-usage {
  padding-bottom: 0;
}
.cache-usage .desktop-directory-actions {
  flex-wrap: wrap;
}
.desktop-directory h3,
.desktop-directory p {
  margin: 0;
}
.desktop-directory-fields {
  display: grid;
  gap: 8px;
}
.desktop-directory-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.desktop-directory-actions input {
  width: auto;
  flex: 1 1 200px;
  font: inherit;
  font-size: 13px;
}
.desktop-directory-actions button {
  padding: 6px 10px;
  border: 1px solid var(--app-border-soft);
  border-radius: 8px;
  background: var(--app-surface);
  color: inherit;
  cursor: pointer;
}
@media (max-width: 600px) {
  .desktop-directory {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }
  .desktop-directory-actions input {
    flex-basis: 100%;
  }
}
</style>

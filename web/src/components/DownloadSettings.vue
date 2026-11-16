<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { requestJson } from '../api/http';

type Settings = {
  mode?: 'local' | 'browser' | 'desktop';
  directory?: string;
  naming: string;
  error: string | null;
  deploymentLocked: boolean;
  canManage: boolean;
};
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
async function load() {
  try {
    settings.value = await requestJson('/api/downloads/settings');
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取下载设置';
  }
}
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
    });
    const failed = response.results.filter((row) => row.status === 'failed');
    result.value = failed.length
      ? `目录已更新；部分迁移未完成：${failed.map((row) => row.file + '：' + row.error).join('；')}。已确认的副本或源文件仍保留。`
      : `保存目录已更新${migrate.value ? `，迁移完成 ${response.results.length} 个文件` : ''}`;
    await load();
    dialog.value?.close();
  } catch (reason) {
    directoryError.value = reason instanceof Error ? reason.message : '目录更改失败';
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
    await requestJson('/api/downloads/settings', {
      method: 'PUT',
      body: JSON.stringify({ naming }),
    });
  } catch {
    error.value = '保存命名格式失败，请重试';
    if (settings.value) settings.value.naming = previous;
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
          <code>{{ settings.directory }}</code
          ><button
            type="button"
            :disabled="settings.deploymentLocked || !settings.canManage || saving"
            @click="openDirectory"
          >
            更改目录
          </button>
        </div>
        <p>这是运行后端那台机器上的目录；只发现目录内的音频，不包含子目录。</p>
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
      <p v-else-if="settings.mode === 'desktop'">每次下载通过 Windows 保存对话框选择位置，可手动修改文件名。</p>
      <p v-else>下载位置由浏览器管理</p>
      <fieldset :disabled="saving || (settings.mode === 'local' && !settings.canManage)">
        <legend>新下载文件命名</legend>
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
      <p v-if="settings.mode === 'desktop'">仅影响之后打开的保存对话框；不会覆盖已有文件，扩展名以实际保存格式为准。任务仅在本次运行保留，暂不支持默认目录、音乐库和转码。</p>
      <p v-else>仅影响之后创建的任务；同名文件自动编号，扩展名以实际保存格式为准。</p>
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
                ><input
                  v-model="location"
                  type="radio"
                  name="library-location"
                  :value="option.id"
                />{{ option.name }}</label
              >
            </fieldset>
            <label
              v-if="location === 'custom'"
              class="path-label"
              >绝对目录路径<input
                v-model="customPath"
                class="path-input"
                type="text"
                :disabled="saving"
                placeholder="粘贴后端机器上的目录路径"
            /></label>
            <label class="migration-choice"
              ><input
                v-model="migrate"
                type="checkbox"
                :disabled="saving"
              />同时迁移旧下载</label
            >
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

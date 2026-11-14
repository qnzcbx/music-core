<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { requestJson } from '../api/http';

const settings = ref<{ directory: string; naming: string; error: string | null }>();
const error = ref('');
const saving = ref(false);
onMounted(async () => {
  try {
    settings.value = await requestJson('/api/downloads/settings');
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取下载设置';
  }
});
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
      <h3>音乐库保存目录</h3>
      <code>{{ settings.directory }}</code>
      <p>
        这是运行后端那台机器上的目录。通过后端 MUSIC_CORE_DOWNLOAD_DIR
        配置，重启后生效；旧文件不会自动移动。
      </p>
      <p
        v-if="settings.error"
        role="alert"
      >
        {{ settings.error }}
      </p>
      <fieldset :disabled="saving">
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
      <p>仅影响之后创建的任务；同名文件自动编号，扩展名以实际保存格式为准。</p>
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

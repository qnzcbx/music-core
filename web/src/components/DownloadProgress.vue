<script setup lang="ts">
import type { DownloadJob } from "../types/music";
defineProps<{ job?: DownloadJob }>();
function sizeLabel(bytes = 0) {
  return `${(bytes / 1000000).toFixed(2)} MB`;
}
</script>
<template>
  <div v-if="job" class="download-status" role="status">
    <template v-if="['queued', 'downloading'].includes(job.state)">
      <progress :value="job.percent ?? undefined" max="100" aria-label="下载进度" />
      <span>
        正在下载 · {{ sizeLabel(job.downloaded_bytes) }}
        <template v-if="job.total_bytes"> / {{ sizeLabel(job.total_bytes) }} </template>
      </span>
    </template>
    <span v-else :class="{ error: job.state === 'failed' }">
      {{ job.message }}
    </span>
    <small v-if="job.selection">
      选择：{{ job.selection.label }} · {{ job.selection.origin === 'current_resolved_media' ? '当前试听表示' : job.source === 'soundcloud' ? '来源原生 Progressive 路线' : '官方指定 ' + job.selection.requestedProviderQualityId }} · 实际档位 {{ job.selection.providerQualityId }}
    </small>
    <small v-if="job.actualMedia">
      成品验证：{{ job.actualMedia.container.toUpperCase() }} · {{ job.actualMedia.codec }} · {{ job.actualMedia.lossless ? '无损编码' : '有损编码' }} · {{ sizeLabel(job.size) }}
    </small>
    <small v-if="job.variant">
      {{ job.variant.container?.toUpperCase() || '容器未知' }}
      <template v-if="job.variant.codec"> · {{ job.variant.codec }}</template>
      <template v-if="job.variant.bitrate"> · {{ Math.round(job.variant.bitrate / 1000) }} kbps</template>
      <template v-if="job.variant.lossless === true"> · 无损（解析证据）</template>
      · {{ job.variant.sizeBytes != null ? sizeLabel(job.variant.sizeBytes) : '大小未知' }}
      · 档位 {{ job.variant.providerQualityId }}
      <template v-if="job.variant.requestedProviderQualityId !== job.variant.providerQualityId">（请求 {{ job.variant.requestedProviderQualityId }}）</template>
    </small>
    <small v-if="job.path">已保存：{{ job.path }}</small>
  </div>
</template>

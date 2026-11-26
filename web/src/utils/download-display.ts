import type { DownloadTask } from '../types/core';

export function formatDownloadBytes(bytes: number | null | undefined) {
  if (bytes == null) return '大小未知';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function downloadStatus(task: DownloadTask) {
  if (task.status === 'failed' && task.errorCode === 'conversion_timeout') return '转换超时';
  if (task.status === 'failed' && task.sourcePreserved) return '转换失败';
  if (task.status === 'failed' && task.errorCode === 'conversion_failed') return '转换失败';
  if (task.phase === 'source_verifying' && task.status === 'downloading') return '正在校验源文件';
  if (task.phase === 'output_verifying' && task.status === 'downloading') return '正在验证转换文件';
  if (task.phase === 'publishing' && task.status === 'downloading') return '正在保存文件';
  if (task.status === 'queued') return '等待下载';
  if (task.status === 'resolving') return '正在获取下载资源…';
  if (task.status === 'downloading' && task.phase === 'transcoding') return '转换中';
  if (task.status === 'downloading' && task.phase === 'verifying') return '正在验证最终文件';
  if (task.status === 'completed') return '已完成';
  if (task.status === 'cancelled') return '已取消';
  if (task.status === 'failed') return downloadError(task.errorCode);
  return task.totalBytes && (task.receivedBytes ?? 0) >= task.totalBytes
    ? '正在校验文件…'
    : '正在下载';
}

export function downloadError(code: string | null | undefined) {
  return (
    (
      {
        download_history_unavailable: '成品已保存，下载记录保存失败',
        source_checksum_failed: '音频校验和不符，未保存成品',
        source_decode_failed: '音频解码校验失败，未保存成品',
        source_duration_mismatch: '音频时长与原曲不符，未保存成品',
        file_exists: '目标文件已存在，请重新选择保存位置',
        source_verification_failed: '源文件校验失败',
        conversion_failed: '转换失败',
        capability_unsupported: '当前无法转换，请尝试保留原格式',
        access_denied: '平台拒绝下载访问',
        media_unavailable: '该版本暂无可下载资源',
        track_not_found: '平台未找到此版本',
        upstream_timeout: '下载或处理超时',
        upstream_failure: '上游网络暂时失败',
        upstream_invalid_response: '文件校验失败或上游响应无效',
        upstream_media_expired: '下载资源已失效',
        untrusted_media: '下载地址未通过安全校验',
        media_capacity: '文件超过下载限制',
        file_io_error: '文件保存失败，请检查目录',
        temporary_cleanup_failed: '临时文件清理失败',
        saved_temporary_cleanup_failed: '成品已保存，临时文件清理失败',
        conversion_cleanup_failed: '无法确认转换进程已退出',
        conversion_timeout: '转换超时',
        internal_error: '服务端处理异常',
      } as Record<string, string>
    )[code ?? ''] ?? '下载失败，服务未返回详细原因'
  );
}

export function downloadPercent(task: DownloadTask) {
  return task.status === 'downloading' &&
    (!task.phase || task.phase === 'downloading') &&
    task.totalBytes &&
    task.totalBytes > 0
    ? Math.min(100, Math.floor(((task.receivedBytes ?? 0) / task.totalBytes) * 100))
    : null;
}

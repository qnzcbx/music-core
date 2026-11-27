import { apiFetch } from './transport';
/** 恢复协调器需要原始HTTP状态及204；open不主动中断，以便关闭晚到Lease。 */
export const playbackRequest: typeof fetch = async (input, init) => {
  const response = await apiFetch(input, init);
  if (!response.ok) {
    const details = await response.clone().json().catch(() => null);
    console.error('播放请求失败', { status: response.status, error: details?.error });
  }
  return response;
};

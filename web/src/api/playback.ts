import { requestJson } from "./http";
import type { TrackIdentity, OpenResponse } from "../types/core";
/** 恢复协调器需要原始HTTP状态及204；open不主动中断，以便关闭晚到Lease。 */
export const playbackRequest: typeof fetch = async (input, init) => {
  const response = await fetch(input, init);
  if (!response.ok) {
    const details = await response.clone().json().catch(() => null);
    console.error('播放请求失败', { status: response.status, error: details?.error });
  }
  return response;
};
export const openPlayback = (identity: TrackIdentity, signal?: AbortSignal) =>
  requestJson<OpenResponse>("/api/playback/open", {
    method: "POST",
    body: JSON.stringify({ identity }),
    signal,
  });
/** close/renew为204响应，接线阶段直接检查HTTP状态，不解析JSON。 */
export async function updateLease(id: string, operation: "close" | "renew", signal?: AbortSignal) {
  const response = await fetch(`/api/playback/${encodeURIComponent(id)}/${operation}`, {
    method: "POST",
    signal,
  });
  if (!response.ok) throw new Error("播放会话操作失败");
}

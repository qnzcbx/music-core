import { ApiError } from './error.ts';
export { ApiError } from './error.ts';

type JsonOptions = RequestInit & {
  errorMessage?: string;
  timeoutMs?: number;
  mutation?: boolean;
};

export async function requestJson<T>(path: string, options: JsonOptions = {}): Promise<T> {
  const { timeoutMs, errorMessage, mutation, signal, ...init } = options;
  signal?.throwIfAborted();
  const controller = new AbortController();
  const timer = mutation && timeoutMs === undefined ? undefined
    : setTimeout(() => controller.abort(), timeoutMs ?? 20000);
  const cancel = () => controller.abort(signal?.reason);
  signal?.addEventListener('abort', cancel, { once: true });
  try {
    const headers = new Headers(init.headers);
    if (init.body) headers.set('Content-Type', 'application/json');
    const response = await fetch(path, { ...init, headers, signal: controller.signal });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      if (mutation && response.status >= 500 && typeof data?.error?.code !== 'string') {
        throw new ApiError(503, '操作结果未确认，请刷新后检查。', 'outcome_unknown');
      }
      const fallback: Record<number, string> = {
        404: '记录不存在或已过期', 409: '当前状态不允许此操作',
        422: '请求信息无效', 429: '服务端暂时无法接受更多任务', 503: '服务暂时不可用',
      };
      throw new ApiError(response.status,
        data?.error?.message ?? errorMessage ?? fallback[response.status] ?? `请求失败（${response.status}）`,
        data?.error?.code, data?.error?.retryable === true);
    }
    if (response.status === 204) return undefined as T;
    try {
      return await response.json() as T;
    } catch {
      if (mutation) throw new ApiError(503, '操作结果未确认，请刷新后检查。', 'outcome_unknown');
      throw new ApiError(502, '服务返回的响应无效', 'invalid_response');
    }
  } catch (error) {
    if (mutation && !(error instanceof ApiError)) {
      throw new ApiError(503, '操作结果未确认，请刷新后检查。', 'outcome_unknown');
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

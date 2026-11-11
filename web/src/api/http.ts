export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}
export async function requestJson<T>(
  path: string,
  options: RequestInit & { errorMessage?: string } = {},
): Promise<T> {
  const timeout = new AbortController(),
    timer = setTimeout(() => timeout.abort(), 20000);
  const cancel = () => timeout.abort();
  if (options.signal?.aborted) timeout.abort();
  options.signal?.addEventListener("abort", cancel, { once: true });
  try {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
      signal: timeout.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok)
      throw new ApiError(
        response.status,
        data?.error?.message ??
          (typeof data?.detail === "string" && data.detail !== "Not Found"
            ? data.detail
            : undefined) ??
          options.errorMessage ??
          (
            {
              404: "记录不存在或已过期",
              409: "当前状态不允许此操作",
              422: "请求信息无效",
              429: "服务端暂时无法接受更多任务",
              503: "服务暂时不可用",
            } as Record<number, string>
          )[response.status] ??
          `请求失败（${response.status}）`,
        data?.error?.code,
      );
    return data as T;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", cancel);
  }
}

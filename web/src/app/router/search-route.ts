/** 路由参数不可信，且可能重复出现（?q=a&q=b）。 */
export function routeSearchQuery(value: unknown): string {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' ? first.trim().slice(0, 80) : ''
}

/** Route input is untrusted and can be repeated (?q=a&q=b). */
export function routeSearchQuery(value: unknown): string {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' ? first.trim().slice(0, 80) : ''
}

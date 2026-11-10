export const SIDEBAR_KEY = 'media-lab.shell.sidebar.v1'

export function readSidebarExpanded(raw: string | null): boolean {
  try {
    const data = JSON.parse(raw ?? 'null')
    return data?.schemaVersion === 1 && data.expanded === true
  } catch { return false }
}

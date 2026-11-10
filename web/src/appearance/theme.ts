export type ThemeMode = 'light' | 'dark' | 'system';
export type EffectiveTheme = Exclude<ThemeMode, 'system'>;
export const APPEARANCE_KEY = 'media-lab.appearance.v1';
export const APPEARANCE = Symbol('appearance');
export function themeMode(value: unknown): ThemeMode {
  return value === 'light' || value === 'dark' ? value : 'system';
}
interface Environment {
  storage?: Pick<Storage, 'getItem' | 'setItem'>;
  media?: Pick<MediaQueryList, 'matches' | 'addEventListener' | 'removeEventListener'>;
  root: Pick<HTMLElement, 'setAttribute'> & { style: Pick<CSSStyleDeclaration, 'colorScheme'> };
}
/** Appearance owns no player/router state, and installs exactly one system listener. */
export function createAppearance({ storage, media, root }: Environment) {
  let mode: ThemeMode = 'system', disposed = false;
  try { mode = themeMode(storage?.getItem(APPEARANCE_KEY)); } catch { /* private/unavailable storage */ }
  const listeners = new Set<() => void>();
  const effective = (): EffectiveTheme => mode === 'system' ? media?.matches ? 'dark' : 'light' : mode;
  function apply() {
    root.setAttribute('data-theme', effective());
    root.setAttribute('data-theme-mode', mode);
    root.style.colorScheme = effective();
    listeners.forEach(listener => listener());
  }
  function systemChanged() { if (!disposed && mode === 'system') apply(); }
  media?.addEventListener('change', systemChanged);
  apply();
  return {
    get mode() { return mode; }, get effective() { return effective(); },
    select(value: ThemeMode) {
      if (disposed) return;
      mode = themeMode(value);
      try { storage?.setItem(APPEARANCE_KEY, mode); } catch { /* selection still works in memory */ }
      apply();
    },
    subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener); },
    dispose() {
      if (disposed) return;
      disposed = true; media?.removeEventListener('change', systemChanged); listeners.clear();
    },
  };
}
export type Appearance = ReturnType<typeof createAppearance>;
export function startAppearance() {
  let storage: Storage | undefined;
  try { storage = window.localStorage; } catch { /* denied storage property access */ }
  return createAppearance({ storage, media: window.matchMedia('(prefers-color-scheme: dark)'), root: document.documentElement });
}

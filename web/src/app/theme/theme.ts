import { createContext } from 'react';

export type ThemeMode = 'light' | 'dark' | 'system';
export type ResolvedTheme = Exclude<ThemeMode, 'system'>;

export interface ThemeContextValue {
  mode: ThemeMode;
  resolvedTheme: ResolvedTheme;
  setMode: (mode: ThemeMode) => void;
}

export const THEME_STORAGE_KEY = 'mldrift.theme';
export const ThemeContext = createContext<ThemeContextValue | null>(null);

export const getSystemTheme = (): ResolvedTheme =>
  window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

export const getStoredTheme = (): ThemeMode => {
  const value = localStorage.getItem(THEME_STORAGE_KEY);
  return value === 'light' || value === 'dark' || value === 'system' ? value : 'system';
};

export const applyTheme = (mode: ThemeMode): ResolvedTheme => {
  const resolved = mode === 'system' ? getSystemTheme() : mode;
  document.documentElement.classList.toggle('dark', resolved === 'dark');
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  return resolved;
};

export function initializeTheme() {
  applyTheme(getStoredTheme());
}

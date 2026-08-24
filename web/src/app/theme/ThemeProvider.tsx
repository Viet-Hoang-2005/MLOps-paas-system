import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  applyTheme,
  getStoredTheme,
  THEME_STORAGE_KEY,
  ThemeContext,
  type ThemeMode,
  type ResolvedTheme,
} from './theme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(getStoredTheme);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => applyTheme(mode));

  const setMode = useCallback((nextMode: ThemeMode) => {
    localStorage.setItem(THEME_STORAGE_KEY, nextMode);
    setModeState(nextMode);
    setResolvedTheme(applyTheme(nextMode));
  }, []);

  useEffect(() => {
    if (mode !== 'system') return undefined;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setResolvedTheme(applyTheme('system'));
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [mode]);

  const value = useMemo(() => ({ mode, resolvedTheme, setMode }), [mode, resolvedTheme, setMode]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

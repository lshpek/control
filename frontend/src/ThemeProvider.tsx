import { useEffect, useState, type ReactNode } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { getTelegramWebApp } from './telegram';
import { isThemeMode, resolveTheme, type ThemeMode } from './theme';

const STORAGE_KEY = 'botvex-theme-mode';

function readInitialMode(): ThemeMode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isThemeMode(stored)) return stored;
  } catch {
    // Storage can be disabled by browser privacy settings; system mode remains usable.
  }
  return 'system';
}

function readSystemPreference(): boolean {
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  return getTelegramWebApp()?.colorScheme === 'dark';
}

export default function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(readInitialMode);
  const [systemPrefersDark, setSystemPrefersDark] = useState(readSystemPreference);

  useEffect(() => {
    const media = typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-color-scheme: dark)')
      : null;
    const telegram = getTelegramWebApp();
    const syncSystemPreference = () => {
      // Prefer the operating system/browser preference. Telegram's scheme is only
      // the fallback when matchMedia is unavailable in the host WebView.
      setSystemPrefersDark(media ? media.matches : telegram?.colorScheme === 'dark');
    };

    media?.addEventListener('change', syncSystemPreference);
    telegram?.onEvent?.('themeChanged', syncSystemPreference);
    syncSystemPreference();
    return () => {
      media?.removeEventListener('change', syncSystemPreference);
      telegram?.offEvent?.('themeChanged', syncSystemPreference);
    };
  }, []);

  const resolvedTheme = resolveTheme(mode, systemPrefersDark);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = resolvedTheme;
    root.style.colorScheme = resolvedTheme;
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // Theme still applies for the current session when storage is unavailable.
    }
  }, [mode, resolvedTheme]);

  return (
    <>
      {children}
      <div className="theme-control" data-testid="theme-control">
        <span className="theme-control-icon" aria-hidden="true">
          {mode === 'system' ? <Monitor size={15} /> : mode === 'light' ? <Sun size={15} /> : <Moon size={15} />}
        </span>
        <label className="theme-control-label" htmlFor="botvex-theme-mode">Тема</label>
        <select
          id="botvex-theme-mode"
          aria-label="Тема оформления"
          value={mode}
          onChange={(event) => {
            const nextMode = event.target.value;
            if (isThemeMode(nextMode)) setMode(nextMode);
          }}
        >
          <option value="system">Системная</option>
          <option value="light">Светлая</option>
          <option value="dark">Тёмная</option>
        </select>
      </div>
    </>
  );
}

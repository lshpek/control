import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ThemeProvider from './ThemeProvider';

const originalTelegram = window.Telegram;
let systemDark = false;
let mediaListeners: Set<EventListenerOrEventListenerObject>;

function installMatchMedia(initialDark: boolean) {
  systemDark = initialDark;
  mediaListeners = new Set();
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn((query: string) => ({
      get matches() { return systemDark; },
      media: query,
      onchange: null,
      addEventListener: vi.fn((_type: string, listener: EventListenerOrEventListenerObject) => mediaListeners.add(listener)),
      removeEventListener: vi.fn((_type: string, listener: EventListenerOrEventListenerObject) => mediaListeners.delete(listener)),
      addListener: vi.fn((listener: EventListener) => mediaListeners.add(listener)),
      removeListener: vi.fn((listener: EventListener) => mediaListeners.delete(listener)),
      dispatchEvent: vi.fn(() => true),
    }) as unknown as MediaQueryList),
  });
}

function changeSystemTheme(isDark: boolean) {
  systemDark = isDark;
  const event = Object.assign(new Event('change'), { matches: isDark, media: '(prefers-color-scheme: dark)' }) as MediaQueryListEvent;
  for (const listener of mediaListeners) {
    if (typeof listener === 'function') listener(event);
    else listener.handleEvent(event);
  }
}

beforeEach(() => {
  window.localStorage.clear();
  delete window.Telegram;
  installMatchMedia(false);
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  document.documentElement.style.removeProperty('color-scheme');
  if (originalTelegram === undefined) delete window.Telegram;
  else window.Telegram = originalTelegram;
  vi.restoreAllMocks();
});

describe('ThemeProvider', () => {
  it('follows system preference and reacts when the system theme changes', async () => {
    render(<ThemeProvider><div>content</div></ThemeProvider>);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'));
    changeSystemTheme(true);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
    changeSystemTheme(false);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'));
  });

  it('persists a manual choice and gives it priority over subsequent system changes', async () => {
    render(<ThemeProvider><div>content</div></ThemeProvider>);
    const select = screen.getByLabelText('Тема оформления');
    fireEvent.change(select, { target: { value: 'dark' } });
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
    expect(window.localStorage.getItem('botvex-theme-mode')).toBe('dark');
    changeSystemTheme(false);
    expect(document.documentElement.dataset.theme).toBe('dark');
    fireEvent.change(select, { target: { value: 'system' } });
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'));
    expect(window.localStorage.getItem('botvex-theme-mode')).toBe('system');
  });

  it('uses a valid saved preference after reload and ignores an invalid stored value', async () => {
    window.localStorage.setItem('botvex-theme-mode', 'light');
    render(<ThemeProvider><div>content</div></ThemeProvider>);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'));
    cleanup();
    window.localStorage.setItem('botvex-theme-mode', 'solarized');
    installMatchMedia(true);
    render(<ThemeProvider><div>content</div></ThemeProvider>);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
  });
});

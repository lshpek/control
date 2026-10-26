export type TelegramEvent = 'themeChanged' | 'viewportChanged' | 'safeAreaChanged' | 'contentSafeAreaChanged';
export type TelegramThemeParams = Partial<Record<
  | 'bg_color'
  | 'secondary_bg_color'
  | 'text_color'
  | 'hint_color'
  | 'link_color'
  | 'button_color'
  | 'button_text_color'
  | 'section_separator_color'
  | 'header_bg_color', string
>>;

export interface TelegramWebApp {
  initData?: string;
  colorScheme?: 'light' | 'dark';
  themeParams?: TelegramThemeParams;
  viewportHeight?: number;
  viewportStableHeight?: number;
  safeAreaInset?: Partial<Record<'top' | 'right' | 'bottom' | 'left', number>>;
  contentSafeAreaInset?: Partial<Record<'top' | 'right' | 'bottom' | 'left', number>>;
  ready?: () => void;
  expand?: () => void;
  onEvent?: (event: TelegramEvent, handler: () => void) => void;
  offEvent?: (event: TelegramEvent, handler: () => void) => void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

const themeVariables: ReadonlyArray<[keyof TelegramThemeParams, string]> = [
  ['bg_color', '--telegram-bg-color'],
  ['secondary_bg_color', '--telegram-secondary-bg-color'],
  ['text_color', '--telegram-text-color'],
  ['hint_color', '--telegram-hint-color'],
  ['link_color', '--telegram-link-color'],
  ['button_color', '--telegram-button-color'],
  ['button_text_color', '--telegram-button-text-color'],
  ['section_separator_color', '--telegram-section-separator-color'],
  ['header_bg_color', '--telegram-header-bg-color'],
];

const insets: ReadonlyArray<[keyof NonNullable<TelegramWebApp['safeAreaInset']>, string]> = [
  ['top', '--tg-safe-area-top'],
  ['right', '--tg-safe-area-right'],
  ['bottom', '--tg-safe-area-bottom'],
  ['left', '--tg-safe-area-left'],
];

function safeHex(value: unknown): string | undefined {
  return typeof value === 'string' && /^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$/.test(value) ? value : undefined;
}

function updateColor(root: HTMLElement, variable: string, value: unknown): void {
  const color = safeHex(value);
  if (color) root.style.setProperty(variable, color);
  else root.style.removeProperty(variable);
}

function updateInsets(root: HTMLElement, prefix: string, values: TelegramWebApp['safeAreaInset']): void {
  for (const [side] of insets) {
    const amount = values?.[side];
    if (typeof amount === 'number' && Number.isFinite(amount) && amount >= 0 && amount <= 1000) {
      root.style.setProperty(`${prefix}${side}`, `${amount}px`);
    } else {
      root.style.removeProperty(`${prefix}${side}`);
    }
  }
}

export function getTelegramWebApp(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp;
}

/** Raw initData only; user identity must be derived and verified by the backend. */
export function getTelegramInitData(): string | undefined {
  const value = getTelegramWebApp()?.initData;
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

/** Initializes the official SDK if present and returns a listener cleanup function. */
export function initTelegramMiniApp(): () => void {
  const webApp = getTelegramWebApp();
  if (!webApp) return () => undefined;

  const root = document.documentElement;
  const updateTheme = () => {
    for (const [key, variable] of themeVariables) updateColor(root, variable, webApp.themeParams?.[key]);
    if (webApp.colorScheme === 'light' || webApp.colorScheme === 'dark') root.dataset.telegramScheme = webApp.colorScheme;
    else delete root.dataset.telegramScheme;
  };
  const updateViewport = () => {
    const dimensions: Array<[number | undefined, string]> = [
      [webApp.viewportHeight, '--tg-viewport-height'],
      [webApp.viewportStableHeight, '--tg-viewport-stable-height'],
    ];
    for (const [value, variable] of dimensions) {
      if (typeof value === 'number' && Number.isFinite(value) && value > 0 && value < 100_000) root.style.setProperty(variable, `${value}px`);
      else root.style.removeProperty(variable);
    }
  };
  const updateSafeArea = () => updateInsets(root, '--tg-safe-area-', webApp.safeAreaInset);
  const updateContentSafeArea = () => updateInsets(root, '--tg-content-safe-area-', webApp.contentSafeAreaInset);

  const safely = (action: (() => void) | undefined) => {
    try { action?.(); } catch { /* Keep the local-browser fallback usable if Telegram's host API fails. */ }
  };
  safely(() => webApp.expand?.());
  updateTheme();
  updateViewport();
  updateSafeArea();
  updateContentSafeArea();
  safely(() => webApp.onEvent?.('themeChanged', updateTheme));
  safely(() => webApp.onEvent?.('viewportChanged', updateViewport));
  safely(() => webApp.onEvent?.('safeAreaChanged', updateSafeArea));
  safely(() => webApp.onEvent?.('contentSafeAreaChanged', updateContentSafeArea));
  safely(() => webApp.ready?.());

  return () => {
    safely(() => webApp.offEvent?.('themeChanged', updateTheme));
    safely(() => webApp.offEvent?.('viewportChanged', updateViewport));
    safely(() => webApp.offEvent?.('safeAreaChanged', updateSafeArea));
    safely(() => webApp.offEvent?.('contentSafeAreaChanged', updateContentSafeArea));
    for (const [, variable] of themeVariables) root.style.removeProperty(variable);
    for (const [, variable] of dimensionsForCleanup) root.style.removeProperty(variable);
    for (const [side] of insets) {
      root.style.removeProperty(`--tg-safe-area-${side}`);
      root.style.removeProperty(`--tg-content-safe-area-${side}`);
    }
    delete root.dataset.telegramScheme;
  };
}

const dimensionsForCleanup: ReadonlyArray<[string, string]> = [
  ['height', '--tg-viewport-height'],
  ['stableHeight', '--tg-viewport-stable-height'],
];

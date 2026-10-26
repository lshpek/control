import {afterEach,describe,expect,it,vi} from 'vitest';
import {getTelegramInitData,initTelegramMiniApp,type TelegramEvent,type TelegramWebApp} from './telegram';

const ROOT=document.documentElement;
const cssVariables=['--telegram-bg-color','--telegram-secondary-bg-color','--telegram-text-color','--telegram-hint-color','--telegram-link-color','--telegram-button-color','--telegram-button-text-color','--telegram-section-separator-color','--tg-viewport-height','--tg-viewport-stable-height'];
const originalTelegram=window.Telegram;

afterEach(()=>{
  if(originalTelegram===undefined)delete window.Telegram;else window.Telegram=originalTelegram;
  ROOT.removeAttribute('data-telegram-scheme');
  for(const variable of cssVariables)ROOT.style.removeProperty(variable);
  vi.restoreAllMocks();
});

describe('Telegram Web App adapter',()=>{
  it('falls back safely when opened in a normal browser',()=>{
    delete window.Telegram;
    expect(getTelegramInitData()).toBeUndefined();
    expect(()=>initTelegramMiniApp()()).not.toThrow();
  });

  it('initializes Telegram, applies theme, viewport and safe-area updates, then removes handlers',()=>{
    const handlers=new Map<string,()=>void>();
    const webApp:TelegramWebApp={
      initData:'raw-init-data',colorScheme:'dark',themeParams:{bg_color:'#101218',button_color:'#6D5CE8'},
      viewportHeight:500,viewportStableHeight:480,safeAreaInset:{top:8,bottom:16},contentSafeAreaInset:{bottom:24},ready:vi.fn(),expand:vi.fn(),
      onEvent:vi.fn((event:TelegramEvent,handler:()=>void)=>{handlers.set(event,handler);}),
      offEvent:vi.fn((event:TelegramEvent)=>{handlers.delete(event);}),
    };
    window.Telegram={WebApp:webApp};
    const cleanup=initTelegramMiniApp();
    expect(getTelegramInitData()).toBe('raw-init-data');
    expect(webApp.ready).toHaveBeenCalledOnce();
    expect(webApp.expand).toHaveBeenCalledOnce();
    expect(ROOT.style.getPropertyValue('--telegram-bg-color')).toBe('#101218');
    expect(ROOT.style.getPropertyValue('--tg-viewport-stable-height')).toBe('480px');
    expect(ROOT.style.getPropertyValue('--tg-safe-area-top')).toBe('8px');
    expect(ROOT.style.getPropertyValue('--tg-content-safe-area-bottom')).toBe('24px');

    webApp.safeAreaInset={top:4,bottom:12};
    webApp.contentSafeAreaInset={bottom:18};
    handlers.get('safeAreaChanged')?.();
    handlers.get('contentSafeAreaChanged')?.();
    expect(ROOT.style.getPropertyValue('--tg-safe-area-top')).toBe('4px');
    expect(ROOT.style.getPropertyValue('--tg-content-safe-area-bottom')).toBe('18px');

    webApp.colorScheme='light';webApp.themeParams={bg_color:'#ffffff',text_color:'#111111',button_color:'#6655cc'};
    handlers.get('themeChanged')?.();
    expect(ROOT.dataset.telegramScheme).toBe('light');
    expect(ROOT.style.getPropertyValue('--telegram-text-color')).toBe('#111111');
    expect(ROOT.style.getPropertyValue('--telegram-button-color')).toBe('#6655cc');
    cleanup();
    expect(webApp.offEvent).toHaveBeenCalledTimes(4);
  });

  it('ignores non-hex theme values rather than placing arbitrary values into CSS',()=>{
    const webApp:TelegramWebApp={themeParams:{bg_color:'red; position:fixed'}};
    window.Telegram={WebApp:webApp};
    const cleanup=initTelegramMiniApp();
    expect(ROOT.style.getPropertyValue('--telegram-bg-color')).toBe('');
    cleanup();
  });
});

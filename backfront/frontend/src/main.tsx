type ScriptLoadState = 'idle' | 'loading' | 'ready' | 'error';

declare global {
  interface Window {
    BackfrontViteRuntime?: {
      appEntryState: ScriptLoadState;
      appEntrySrc: string;
    };
  }
}

const APP_ENTRY_SRC = '/js/app.entry.js?v=20260521-vite-auth-redirect';

function loadClassicScript(src: string): Promise<void> {
  const existing = Array.from(document.scripts).find((script) => {
    const current = script.getAttribute('src') || '';
    return current.split(/[?#]/)[0] === src.split(/[?#]/)[0];
  });
  if (existing) return Promise.resolve();

  window.BackfrontViteRuntime = {
    appEntryState: 'loading',
    appEntrySrc: src,
  };

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.onload = () => {
      window.BackfrontViteRuntime = {
        appEntryState: 'ready',
        appEntrySrc: src,
      };
      resolve();
    };
    script.onerror = () => {
      window.BackfrontViteRuntime = {
        appEntryState: 'error',
        appEntrySrc: src,
      };
      reject(new Error(`Failed to load app entrypoint: ${src}`));
    };
    document.body.appendChild(script);
  });
}

window.BackfrontViteRuntime = {
  appEntryState: 'idle',
  appEntrySrc: APP_ENTRY_SRC,
};

loadClassicScript(APP_ENTRY_SRC).catch((error) => {
  console.error('[Vite runtime]', error);
  const container = document.getElementById('backfront-app-root');
  if (container) {
    container.innerHTML = '<div class="error-box">Не удалось загрузить страницу приложения.</div>';
  }
});

export {};

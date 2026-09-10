/* Legacy global actions shared by mixed HTML/React pages */
'use strict';

(function initBackfrontLegacyActions() {
  window.BackfrontActions = window.BackfrontActions || {};

  function clearFrontendRuntimeState() {
    try {
      const exactKeys = new Set([
        'xfiles.currentLead',
        'leadApp.currentLead',
        'leadApp.lastLead',
        'xfiles.chat.current',
      ]);
      const prefixes = [
        'leadApp.',
        'gridApp.',
        'importApp.',
        'chatAnalysis.',
        'xfiles.chat',
        'xfiles.leads',
      ];
      [window.localStorage, window.sessionStorage].forEach((storage) => {
        if (!storage) return;
        Object.keys(storage).forEach((key) => {
          if (exactKeys.has(key) || prefixes.some((prefix) => key.startsWith(prefix))) {
            storage.removeItem(key);
          }
        });
      });
    } catch (_) {
      // Best-effort cleanup: backend reset remains authoritative.
    }
  }

  function notify(message, isError = false) {
    if (window.BackfrontDebug?.[isError ? 'error' : 'log']) {
      window.BackfrontDebug[isError ? 'error' : 'log'](message);
    }
    if (isError) window.alert(message);
  }

  async function runTelegramAuthAction(config) {
    const {
      confirmText,
      endpoint,
      successMessage,
      errorMessage,
    } = config;
    if (typeof window.confirm === 'function' && !window.confirm(confirmText)) return;
    try {
      const result = await window.BackfrontApi.apiPostJson(endpoint, {}, { timeoutMs: 30000 });
      clearFrontendRuntimeState();
      notify(result?.message || successMessage);
      window.location.href = '/setup_wizard.html';
    } catch (error) {
      notify(`${errorMessage}: ${String(error?.message || error)}`, true);
    }
  }

  window.BackfrontClearRuntimeState = window.BackfrontClearRuntimeState || clearFrontendRuntimeState;

  if (!window.BackfrontActions.reauthorizeTelegram) {
    window.BackfrontActions.reauthorizeTelegram = async function reauthorizeTelegramFromMenu() {
      return runTelegramAuthAction({
        confirmText: 'Сбросить текущую Telegram-сессию и пройти авторизацию заново?',
        endpoint: window.BackfrontApi.endpoints.auth.reauthorize,
        successMessage: 'Telegram-сессия сброшена. Открою мастер настройки.',
        errorMessage: 'Не удалось запустить переавторизацию Telegram',
      });
    };
  }

  if (!window.BackfrontActions.logoutTelegram) {
    window.BackfrontActions.logoutTelegram = async function logoutTelegramFromMenu() {
      return runTelegramAuthAction({
        confirmText: 'Выйти из Telegram и удалить сохранённую авторизацию?',
        endpoint: window.BackfrontApi.endpoints.auth.logout,
        successMessage: 'Telegram-сессия удалена. Открою мастер настройки.',
        errorMessage: 'Не удалось выйти из Telegram',
      });
    };
  }
})();

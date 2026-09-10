/* Debug logger separated from page controllers */
'use strict';

(function initBackfrontDebugClient() {
  if (window.BackfrontDebug) return;

  function isEnabled() {
    try {
      const globalValue = window.XFILES_DEBUG ?? window.BACKFRONT_DEBUG;
      if (globalValue != null) {
        return ['1', 'true', 'yes', 'on'].includes(String(globalValue).toLowerCase());
      }
      const stored = window.localStorage?.getItem('backfront.debug');
      return ['1', 'true', 'yes', 'on'].includes(String(stored || '').toLowerCase());
    } catch (_) {
      return false;
    }
  }

  function log(...args) {
    if (isEnabled()) console.log(...args);
  }

  function warn(...args) {
    if (isEnabled()) console.warn(...args);
  }

  function error(...args) {
    console.error(...args);
  }

  window.BackfrontDebug = {
    isEnabled,
    log,
    warn,
    error,
  };
})();

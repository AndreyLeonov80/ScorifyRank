/* DOM adapter for legacy.lead.store.js side effects. */
'use strict';

(function initLegacyLeadDom() {
  window.BackfrontLeadDom = {
    byId(id) {
      return document.getElementById(id);
    },
    addDocumentListener(type, handler, options) {
      document.addEventListener(type, handler, options);
      return () => document.removeEventListener(type, handler, options);
    },
    confirm(message) {
      return window.confirm(message);
    },
    isDocumentHidden() {
      return !!document.hidden;
    },
    getStorage(key) {
      try {
        return String(localStorage.getItem(key) || '').trim();
      } catch (_) {
        return '';
      }
    },
    setStorage(key, value) {
      try {
        localStorage.setItem(key, value);
      } catch (_) {}
    },
    removeStorage(key) {
      try {
        localStorage.removeItem(key);
      } catch (_) {}
    },
    requestFrame(callback) {
      return window.requestAnimationFrame(callback);
    },
    setTimeout(callback, delay) {
      return window.setTimeout(callback, delay);
    },
  };
})();

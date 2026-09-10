/* React runtime bridge for legacy Backfront stores */
'use strict';

(function initBackfrontReactRuntime() {
  if (!window.React || !window.ReactDOM || !window.htm) {
    console.error('[React] Runtime libraries are not loaded');
    return;
  }

  const ReactApi = window.React;
  const html = window.htm.bind(ReactApi.createElement);

  function isReactiveContainer(value) {
    if (!value || typeof value !== 'object') return false;
    if (Array.isArray(value)) return true;
    const proto = Object.getPrototypeOf(value);
    return proto === Object.prototype || proto === null;
  }

  function createReactiveLegacyStore(factory) {
    let version = 0;
    let notifyScheduled = false;
    const listeners = new Set();
    const proxyCache = new WeakMap();
    const fnCache = new WeakMap();
    const rootRef = { current: null };

    function subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }

    function getSnapshot() {
      return version;
    }

    function notify() {
      if (notifyScheduled) return;
      notifyScheduled = true;
      queueMicrotask(() => {
        notifyScheduled = false;
        version += 1;
        for (const listener of listeners) listener();
      });
    }

    function unwrap(value) {
      return value && typeof value === 'object' && value.__raw ? value.__raw : value;
    }

    function bindMethod(receiver, prop, value) {
      let cache = fnCache.get(receiver);
      if (!cache) {
        cache = new Map();
        fnCache.set(receiver, cache);
      }
      if (!cache.has(prop)) {
        cache.set(prop, function boundLegacyMethod(...args) {
          return value.apply(receiver, args.map(unwrap));
        });
      }
      return cache.get(prop);
    }

    function proxify(target) {
      if (!isReactiveContainer(target)) return target;
      if (proxyCache.has(target)) return proxyCache.get(target);

      const proxy = new Proxy(target, {
        get(obj, prop, receiver) {
          if (prop === '__raw') return obj;
          if (prop === '__notify') return notify;
          const value = Reflect.get(obj, prop, receiver);
          if (typeof value === 'function') {
            return bindMethod(receiver, prop, value);
          }
          return proxify(value);
        },
        set(obj, prop, value) {
          const next = unwrap(value);
          const prev = obj[prop];
          const result = Reflect.set(obj, prop, next);
          if (prev !== next) notify();
          return result;
        },
        deleteProperty(obj, prop) {
          const existed = Object.prototype.hasOwnProperty.call(obj, prop);
          const result = Reflect.deleteProperty(obj, prop);
          if (existed && result) notify();
          return result;
        },
      });

      proxyCache.set(target, proxy);
      return proxy;
    }

    const raw = factory();
    raw.$nextTick = (cb) => Promise.resolve().then(cb);
    const store = proxify(raw);
    rootRef.current = store;

    return {
      store,
      subscribe,
      getSnapshot,
      destroy() {
        const stopMethods = [
          'stopAuthPolling',
          'stopLeadPolling',
          'stopGlobalLeadStream',
          'closeStream',
          'stopLlmPolling',
          'stopPolling',
          'stopStatusStream',
        ];
        for (const methodName of stopMethods) {
          try { store[methodName]?.(); } catch {}
        }
      },
    };
  }

  function useLegacyStore(factory) {
    const bridgeRef = ReactApi.useRef(null);
    if (!bridgeRef.current) {
      bridgeRef.current = createReactiveLegacyStore(factory);
    }
    const bridge = bridgeRef.current;
    ReactApi.useSyncExternalStore(bridge.subscribe, bridge.getSnapshot, bridge.getSnapshot);
    ReactApi.useEffect(() => () => bridge.destroy(), [bridge]);
    return bridge.store;
  }

  function useDebouncedCallback(callback, delayMs) {
    const cbRef = ReactApi.useRef(callback);
    const timerRef = ReactApi.useRef(null);
    cbRef.current = callback;

    ReactApi.useEffect(() => () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    }, []);

    return ReactApi.useCallback((...args) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => cbRef.current(...args), delayMs);
    }, [delayMs]);
  }

  class BackfrontErrorBoundary extends ReactApi.Component {
    constructor(props) {
      super(props);
      this.state = { error: null };
    }

    static getDerivedStateFromError(error) {
      return { error };
    }

    componentDidCatch(error, info) {
      console.error('[React ErrorBoundary]', error, info);
    }

    render() {
      if (!this.state.error) return this.props.children;
      const message = String(this.state.error?.message || this.state.error || 'unknown error');
      return html`
        <div className="error-box" role="alert">
          <strong>Страница не смогла отрисоваться.</strong>
          <div>Ошибка: ${message}</div>
          <button type="button" onClick=${() => window.location.reload()}>Обновить страницу</button>
        </div>
      `;
    }
  }

  function withErrorBoundary(node) {
    return html`<${BackfrontErrorBoundary}>${node}<//>`;
  }

  function patchCreateRootWithBoundary() {
    const reactDom = window.ReactDOM;
    if (!reactDom || reactDom.__backfrontBoundaryPatched || typeof reactDom.createRoot !== 'function') return;
    const originalCreateRoot = reactDom.createRoot.bind(reactDom);
    reactDom.createRoot = function createRootWithBackfrontBoundary(...args) {
      const root = originalCreateRoot(...args);
      const originalRender = root.render.bind(root);
      root.render = (node) => originalRender(withErrorBoundary(node));
      return root;
    };
    reactDom.__backfrontBoundaryPatched = true;
  }

  patchCreateRootWithBoundary();

  window.BackfrontReact = {
    React: ReactApi,
    ReactDOM: window.ReactDOM,
    html,
    ErrorBoundary: BackfrontErrorBoundary,
    withErrorBoundary,
    useLegacyStore,
    useDebouncedCallback,
  };
})();

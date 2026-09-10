/* React routes page: Moscow address extraction and Yandex map */
'use strict';

(function mountReactRoutesPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared) {
    console.error('[React] Routes runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html } = window.BackfrontReact;
  const { ErrorBox, PageHeader, TablePaginationFooter, LoadingNotice } = window.BackfrontReactShared;

  const MAP_SCRIPT_URL = 'https://api-maps.yandex.ru/2.1/?lang=ru_RU';

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { Accept: 'application/json', ...(options.headers || {}) },
      cache: 'no-store',
    });
    if (!response.ok) {
      let body = '';
      try { body = await response.text(); } catch (_) {}
      throw new Error(`HTTP ${response.status} ${response.statusText}${body ? ' — ' + body : ''}`);
    }
    return response.json();
  }

  function pageWindow(page, totalPages) {
    const total = Math.max(1, Number(totalPages || 1));
    const current = Math.max(1, Math.min(Number(page || 1), total));
    const start = Math.max(1, current - 2);
    const end = Math.min(total, start + 4);
    return Array.from({ length: end - start + 1 }, (_, index) => start + index);
  }

  function fmtDate(value) {
    return window.fmtDate ? window.fmtDate(value, true) : (value || '—');
  }

  function MetricCard({ label, value, note, tone = 'ok' }) {
    return html`
      <div className=${`metric-card ${tone === 'warn' ? 'warn' : ''}`}>
        <div className="metric-label">${label}</div>
        <div className="metric-value">${value}</div>
        <div className="subtle">${note || ''}</div>
      </div>
    `;
  }

  function RoutesPage() {
    const [status, setStatus] = React.useState(null);
    const [addresses, setAddresses] = React.useState({ items: [], total: 0, page: 1, page_size: 10, total_pages: 1 });
    const [mapAddresses, setMapAddresses] = React.useState([]);
    const [messages, setMessages] = React.useState({ items: [], total: 0, page: 1, page_size: 10, total_pages: 1 });
    const [models, setModels] = React.useState([]);
    const [selectedModel, setSelectedModel] = React.useState('');
    const [modelQuery, setModelQuery] = React.useState('');
    const [showPaidModels, setShowPaidModels] = React.useState(false);
    const [query, setQuery] = React.useState('');
    const [pageSize, setPageSize] = React.useState(5);
    const [addressPage, setAddressPage] = React.useState(1);
    const [messagePage, setMessagePage] = React.useState(1);
    const [onlyWithAddress, setOnlyWithAddress] = React.useState(false);
    const [error, setError] = React.useState('');
    const [mapStatus, setMapStatus] = React.useState('Карта загружается…');
    const [mapPoints, setMapPoints] = React.useState(0);
    const mapRef = React.useRef(null);
    const clustererRef = React.useRef(null);
    const geocodedRef = React.useRef(new Set());

    const loadStatus = React.useCallback(async () => {
      const data = await fetchJson('/api/payme/routes/status');
      setStatus(data);
      return data;
    }, []);

    const loadAddresses = React.useCallback(async (page = addressPage) => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), query });
      const data = await fetchJson(`/api/payme/routes/addresses?${params.toString()}`);
      setAddresses(data);
    }, [addressPage, pageSize, query]);

    const loadMapAddresses = React.useCallback(async () => {
      const params = new URLSearchParams({ query, limit: '5000' });
      const data = await fetchJson(`/api/payme/routes/map-points?${params.toString()}`);
      setMapAddresses(Array.isArray(data.items) ? data.items : []);
    }, [query]);

    const loadMessages = React.useCallback(async (page = messagePage) => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        query,
        only_with_address: String(onlyWithAddress),
      });
      const data = await fetchJson(`/api/payme/routes/messages?${params.toString()}`);
      setMessages(data);
    }, [messagePage, pageSize, query, onlyWithAddress]);

    const loadModels = React.useCallback(async ({ queryText = modelQuery, includePaid = showPaidModels } = {}) => {
      const params = new URLSearchParams({
        query: queryText || '',
        include_paid: includePaid ? 'true' : 'false',
      });
      const data = await fetchJson(`/api/payme/openrouter/models?${params.toString()}`);
      const items = Array.isArray(data.items) ? data.items : [];
      setModels(items);
      return items;
    }, [modelQuery, showPaidModels]);

    const loadSettings = React.useCallback(async () => {
      const data = await fetchJson('/api/payme/settings');
      const model = String(data.openrouter_model || '').trim();
      setSelectedModel(model);
      setShowPaidModels(Boolean(data.openrouter_show_paid_models));
      await loadModels({ includePaid: Boolean(data.openrouter_show_paid_models), queryText: modelQuery });
    }, [loadModels, modelQuery]);

    const reloadAll = React.useCallback(async () => {
      try {
        setError('');
        await Promise.all([loadStatus(), loadAddresses(addressPage), loadMapAddresses(), loadMessages(messagePage)]);
      } catch (err) {
        setError(String(err?.message || err || 'Не удалось загрузить маршруты'));
      }
    }, [loadStatus, loadAddresses, loadMapAddresses, loadMessages, addressPage, messagePage]);

    React.useEffect(() => {
      reloadAll();
    }, [reloadAll]);

    React.useEffect(() => {
      loadSettings().catch((err) => setError(String(err?.message || err || 'Не удалось загрузить модели OpenRouter')));
    }, []);

    React.useEffect(() => {
      const timer = window.setInterval(async () => {
        try {
          const next = await loadStatus();
          if (next?.running) {
            await Promise.all([loadAddresses(addressPage), loadMapAddresses(), loadMessages(messagePage)]);
          }
        } catch (_) {}
      }, 2000);
      return () => window.clearInterval(timer);
    }, [loadStatus, loadAddresses, loadMapAddresses, loadMessages, addressPage, messagePage]);

    React.useEffect(() => {
      let cancelled = false;
      if (window.ymaps) return;
      const existing = document.querySelector(`script[src="${MAP_SCRIPT_URL}"]`);
      if (existing) return;
      const script = document.createElement('script');
      script.src = MAP_SCRIPT_URL;
      script.async = true;
      script.onload = () => {
        if (!cancelled) setMapStatus('Yandex Maps загружена');
      };
      script.onerror = () => {
        if (!cancelled) setMapStatus('Не удалось загрузить Yandex Maps');
      };
      document.head.appendChild(script);
      return () => { cancelled = true; };
    }, []);

    React.useEffect(() => {
      let cancelled = false;
      const initMap = () => {
        if (cancelled || !window.ymaps || mapRef.current) return;
        window.ymaps.ready(() => {
          if (cancelled || mapRef.current) return;
          mapRef.current = new window.ymaps.Map('routes-map', {
            center: [55.751244, 37.618423],
            zoom: 10,
            controls: ['zoomControl', 'fullscreenControl'],
          });
          setMapStatus('Карта Москвы готова');
        });
      };
      initMap();
      const timer = window.setInterval(initMap, 700);
      return () => {
        cancelled = true;
        window.clearInterval(timer);
      };
    }, []);

    React.useEffect(() => {
      if (!window.ymaps || !mapRef.current) return;
      const map = mapRef.current;
      if (clustererRef.current) {
        try { map.geoObjects.remove(clustererRef.current); } catch (_) {}
      }
      clustererRef.current = new window.ymaps.Clusterer({
        preset: 'islands#invertedBlueClusterIcons',
        groupByCoordinates: false,
        clusterDisableClickZoom: false,
        clusterOpenBalloonOnClick: true,
      });

      const rows = Array.isArray(mapAddresses) ? mapAddresses : [];
      if (!rows.length) {
        setMapPoints(0);
        return;
      }
      let active = true;
      const placemarks = [];
      const addPoint = (row, coords) => {
        if (!active || !coords) return;
        const placemark = new window.ymaps.Placemark(coords, {
          balloonContentHeader: row.address,
          balloonContentBody: `${row.messages_count || 0} сообщений<br>${(row.leads || []).join(', ')}`,
          clusterCaption: row.address,
          hintContent: row.address,
        }, {
          preset: 'islands#blueDotIcon',
        });
        placemarks.push(placemark);
        clustererRef.current.add(placemark);
        setMapPoints(placemarks.length);
        try { map.geoObjects.add(clustererRef.current); } catch (_) {}
        if (placemarks.length > 1) {
          try { map.setBounds(clustererRef.current.getBounds(), { checkZoomRange: true, zoomMargin: 32 }); } catch (_) {}
        } else {
          try { map.setCenter(coords, 14, { duration: 200 }); } catch (_) {}
        }
      };
      rows.slice(0, 500).forEach((row) => {
        if (row.lat != null && row.lon != null) {
          addPoint(row, [Number(row.lat), Number(row.lon)]);
          return;
        }
        const address = String(row.address || '').trim();
        const addressKey = String(row.address_key || address).trim();
        if (!address || geocodedRef.current.has(addressKey)) return;
        geocodedRef.current.add(addressKey);
        window.ymaps.geocode(`${address}, Москва`, { results: 1 })
          .then((result) => {
            const first = result.geoObjects.get(0);
            const coords = first?.geometry?.getCoordinates?.();
            if (!coords) return;
            addPoint(row, coords);
            fetchJson('/api/payme/routes/geocode', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ address_key: addressKey, lat: coords[0], lon: coords[1] }),
            }).catch(() => {});
          })
          .catch(() => {});
      });
      return () => {
        active = false;
      };
    }, [mapAddresses, mapStatus]);

    async function runRefresh(forceFull = false) {
      if (forceFull) {
        const confirmFullRefresh = typeof window.confirmLongRebuild === 'function'
          ? window.confirmLongRebuild(
            'Полный пересчёт маршрутов',
            'Будут заново проверены сообщения с Москвой, адреса и геокодинг. Это может занять время, поэтому операция пойдёт в фоне.'
          )
          : (typeof window.confirm !== 'function' || window.confirm('Полный пересчёт маршрутов может занять время.\n\nПродолжить?'));
        if (!confirmFullRefresh) return;
      }
      try {
        setError('');
        const params = new URLSearchParams({
          force_full: forceFull ? 'true' : 'false',
          confirm_full_refresh: forceFull ? 'true' : 'false',
          model: selectedModel || '',
        });
        await fetchJson(`/api/payme/routes/refresh?${params.toString()}`, { method: 'POST' });
        await reloadAll();
      } catch (err) {
        setError(String(err?.message || err || 'Не удалось запустить маршруты'));
      }
    }

    const progress = Math.max(0, Math.min(100, Number(status?.progress_percent || 0)));
    const logRows = Array.isArray(status?.progress_log) ? status.progress_log : [];

    return html`
      <div className="page">
        <${PageHeader}
          title="Маршруты"
          subtitle="Москва в сообщениях, OpenRouter-извлечение адресов и карта точек для маршрутизации."
          active="routes"
        />

        <section className="toolbar">
          <div className="toolbar-group">
            <input className="input" style=${{ minWidth: '320px' }} placeholder="Поиск по адресу, чату или сообщению…" value=${query} onChange=${(event) => setQuery(event.target.value)} />
            <select className="select" value=${String(pageSize)} onChange=${(event) => { setPageSize(Number(event.target.value)); setAddressPage(1); setMessagePage(1); }}>
              <option value="5">5 строк</option>
              <option value="10">10 строк</option>
              <option value="20">20 строк</option>
              <option value="50">50 строк</option>
              <option value="100">100 строк</option>
            </select>
            <label className="chip"><input type="checkbox" checked=${onlyWithAddress} onChange=${(event) => setOnlyWithAddress(event.target.checked)} /> Только с адресом</label>
          </div>
          <div className="toolbar-group">
            <button className="btn" onClick=${() => reloadAll()}>Обновить</button>
            <button className="btn btn-active" disabled=${!!status?.running} onClick=${() => runRefresh(false)}>${status?.running ? 'Анализ идёт…' : 'Запустить анализ'}</button>
            <button className="btn" disabled=${!!status?.running} onClick=${() => runRefresh(true)}>Пересчитать всё</button>
          </div>
        </section>

        <${ErrorBox} error=${error} tag="section" />

        <section className="panel">
          <div className="section-title">Модель OpenRouter для расчёта маршрутов</div>
          <div className="section-subtitle subtle">
            Выберите модель перед запуском анализа. Это влияет на извлечение адресов из полного текста сообщений.
            Текущая модель: <strong>${selectedModel || status?.openrouter_model || '—'}</strong>
          </div>
          <div className="toolbar" style=${{ paddingTop: 0 }}>
            <div className="toolbar-group" style=${{ flex: 1 }}>
              <input className="input" style=${{ minWidth: '260px', flex: 1 }} placeholder="Поиск модели…" value=${modelQuery} onChange=${(event) => setModelQuery(event.target.value)} />
              <label className="chip"><input type="checkbox" checked=${showPaidModels} onChange=${(event) => setShowPaidModels(event.target.checked)} /> Показать платные</label>
              <button className="btn" onClick=${() => loadModels({ queryText: modelQuery, includePaid: showPaidModels })}>Найти модели</button>
            </div>
            <select className="select" style=${{ minWidth: '360px' }} value=${selectedModel} onChange=${(event) => setSelectedModel(event.target.value)}>
              ${selectedModel && !models.some((model) => model.id === selectedModel) ? html`<option value=${selectedModel}>${selectedModel} (текущая)</option>` : null}
              ${models.map((model) => html`
                <option key=${model.id} value=${model.id}>${model.name || model.id}${model.free ? ' · free' : ''}</option>
              `)}
            </select>
          </div>
        </section>

        <section className="metrics-grid">
          <${MetricCard} label="Москва" value=${status?.moscow_messages_total || 0} note="сообщений со словом Москва" />
          <${MetricCard} label="Адреса" value=${status?.addresses_found || 0} note="уникальных адресов в справочнике" />
          <${MetricCard} label="GPS" value=${mapPoints || status?.gps_points || 0} note="точек/кластеров на карте" />
          <${MetricCard} label="Статус" value=${status?.running ? 'running' : 'idle'} note=${status?.progress_label || 'ожидание'} tone=${status?.running ? 'warn' : 'ok'} />
        </section>

        <section className="panel">
          <div className="section-title">Прогресс обработки</div>
          <div className="section-subtitle subtle">
            ${status?.progress_label || 'Маршруты готовы к запуску'} · ${status?.progress_current || 0} из ${status?.progress_total || 0}
            ${status?.current_item ? html` · текущий источник: <strong>${status.current_item}</strong>` : null}
          </div>
          <div className="progress-bar"><span style=${{ width: `${progress}%` }} /></div>
        </section>

        <section className="map-grid">
          <div className="map-box"><div id="routes-map"></div></div>
          <div className="panel" style=${{ margin: 0 }}>
            <div className="section-title">Лог маршрутов</div>
            <div className="section-subtitle subtle">${mapStatus}</div>
            <div className="log-box">
              ${logRows.length ? logRows.map((row, index) => html`<div className="log-row" key=${index}>${row}</div>`) : html`<div className="empty">Лог появится после запуска анализа.</div>`}
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="section-title">Справочник адресов</div>
          <div className="section-subtitle subtle">Дубли адресов объединяются по нормализованному ключу.</div>
          <div className="table-wrap">
            ${!addresses.items.length ? html`<${LoadingNotice} message="Адреса пока не найдены" details="Нажмите “Запустить анализ”, чтобы OpenRouter извлёк адреса из сообщений с Москва." />` : html`
              <table>
                <thead><tr><th>Адрес</th><th>Сообщений</th><th>Чаты</th><th>GPS</th><th>Пример</th></tr></thead>
                <tbody>
                  ${addresses.items.map((row) => html`
                    <tr key=${row.address_key}>
                      <td><div className="font-semibold">${row.address}</div><div className="subtle">${row.address_key}</div></td>
                      <td><strong>${row.messages_count || 0}</strong></td>
                      <td><div className="cell-text">${(row.leads || []).join(', ') || '—'}</div></td>
                      <td>${row.lat != null && row.lon != null ? html`<span className="badge badge-active">${Number(row.lat).toFixed(5)}, ${Number(row.lon).toFixed(5)}</span>` : html`<span className="badge badge-warn">геокодируется</span>`}</td>
                      <td><div className="cell-text">${row.examples?.[0]?.text || '—'}</div></td>
                    </tr>
                  `)}
                </tbody>
              </table>
            `}
          </div>
          <${TablePaginationFooter}
            rangeText=${addresses.total ? `${(addresses.page - 1) * addresses.page_size + 1}-${Math.min(addresses.total, addresses.page * addresses.page_size)} из ${addresses.total}` : '0 из 0'}
            page=${addresses.page}
            totalPages=${addresses.total_pages}
            pageWindow=${pageWindow(addresses.page, addresses.total_pages)}
            onPrev=${() => { const next = Math.max(1, addressPage - 1); setAddressPage(next); loadAddresses(next); }}
            onNext=${() => { const next = Math.min(addresses.total_pages, addressPage + 1); setAddressPage(next); loadAddresses(next); }}
            onGo=${(page) => { setAddressPage(page); loadAddresses(page); }}
          />
        </section>

        <section className="panel">
          <div className="section-title">Сообщения с Москва</div>
          <div className="section-subtitle subtle">Полные сообщения, по которым OpenRouter ищет адрес.</div>
          <div className="table-wrap">
            ${!messages.items.length ? html`<div className="empty">Сообщения пока не загружены. Запустите анализ маршрутов.</div>` : html`
              <table>
                <thead><tr><th>Дата</th><th>Чат</th><th>Адрес</th><th>Сообщение</th><th>Статус</th></tr></thead>
                <tbody>
                  ${messages.items.map((row) => html`
                    <tr key=${row.row_key || row.row_hash}>
                      <td><div>${fmtDate(row.date_utc)}</div><div className="subtle">#${row.message_id}</div></td>
                      <td><div className="font-semibold">${row.lead || '—'}</div><div className="subtle">${row.source_selector || '—'}</div></td>
                      <td><div className="cell-text">${row.address || '—'}</div><div className="subtle">${row.confidence ? `${Math.round(Number(row.confidence) * 100)}%` : ''}</div></td>
                      <td><div className="cell-text">${row.text || '—'}</div></td>
                      <td><span className=${`badge ${row.address ? 'badge-active' : row.address_source === 'pending' ? 'badge-pending' : 'badge-warn'}`}>${row.address_source || 'pending'}</span></td>
                    </tr>
                  `)}
                </tbody>
              </table>
            `}
          </div>
          <${TablePaginationFooter}
            rangeText=${messages.total ? `${(messages.page - 1) * messages.page_size + 1}-${Math.min(messages.total, messages.page * messages.page_size)} из ${messages.total}` : '0 из 0'}
            page=${messages.page}
            totalPages=${messages.total_pages}
            pageWindow=${pageWindow(messages.page, messages.total_pages)}
            onPrev=${() => { const next = Math.max(1, messagePage - 1); setMessagePage(next); loadMessages(next); }}
            onNext=${() => { const next = Math.min(messages.total_pages, messagePage + 1); setMessagePage(next); loadMessages(next); }}
            onGo=${(page) => { setMessagePage(page); loadMessages(page); }}
          />
        </section>
      </div>
    `;
  }

  const root = document.getElementById('react-root');
  if (!root) {
    console.error('[React] Root container #react-root was not found');
    return;
  }
  ReactDOM.createRoot(root).render(html`<${RoutesPage} />`);
})();

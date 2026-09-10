/* React calendar page for event dates extracted by OpenRouter */
'use strict';

(function mountReactCalendarPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared) {
    console.error('[React] Calendar runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useDebouncedCallback } = window.BackfrontReact;
  const { ErrorBox, PageHeader, TablePaginationFooter, LoadingNotice, Modal } = window.BackfrontReactShared;

  const MONTH_NAMES = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
  ];
  const MONTH_NAMES_GENITIVE = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
  ];
  const WEEK_DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

  function monthStart(date) {
    return new Date(date.getFullYear(), date.getMonth(), 1);
  }

  function addMonths(date, delta) {
    return new Date(date.getFullYear(), date.getMonth() + delta, 1);
  }

  function toYmd(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function monthEndYmd(date) {
    return toYmd(new Date(date.getFullYear(), date.getMonth() + 1, 0));
  }

  function calendarDaysForMonth(date) {
    const start = monthStart(date);
    const mondayOffset = (start.getDay() + 6) % 7;
    const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate() - mondayOffset);
    return Array.from({ length: 42 }, (_, index) => {
      const item = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate() + index);
      return {
        date: item,
        ymd: toYmd(item),
        inMonth: item.getMonth() === date.getMonth(),
        isWeekend: [5, 6].includes((item.getDay() + 6) % 7),
      };
    });
  }

  function eventAuthor(row) {
    return row.sender_username ? `@${row.sender_username}` : (row.sender_name || '—');
  }

  function formatDateTime(value) {
    return window.fmtDate ? window.fmtDate(value, true) : (value || '—');
  }

  function dayLabel(date) {
    const day = date.getDate();
    return day === 1 ? `${day} ${MONTH_NAMES_GENITIVE[date.getMonth()]}` : String(day);
  }

  function EventPopup({ row, onClose }) {
    if (!row) return null;
    return html`
      <${Modal}
        open=${Boolean(row)}
        onClose=${onClose}
        title=${row.lead || 'Событие'}
        subtitle=${row.source_selector || 'selector не указан'}
        ariaLabel="Детали события"
        backdropClassName="event-modal-backdrop"
        className="event-modal"
        headerClassName="event-modal-head"
        titleClassName="event-modal-title"
        bodyClassName="event-modal-body"
      >
        <div className="event-detail-grid">
          <div className="event-detail">
            <div className="event-detail-label">Дата мероприятия</div>
            <div className="event-detail-value">${row.event_date || '—'}</div>
          </div>
          <div className="event-detail">
            <div className="event-detail-label">Дата сообщения</div>
            <div className="event-detail-value">${formatDateTime(row.date_utc)}</div>
          </div>
          <div className="event-detail">
            <div className="event-detail-label">Автор</div>
            <div className="event-detail-value">${eventAuthor(row)}</div>
          </div>
          <div className="event-detail">
            <div className="event-detail-label">Message ID</div>
            <div className="event-detail-value">${row.message_id ?? '—'}</div>
          </div>
          <div className="event-detail">
            <div className="event-detail-label">Ключевые слова</div>
            <div className="event-detail-value">${Array.isArray(row.matched_keywords) && row.matched_keywords.length ? row.matched_keywords.join(', ') : '—'}</div>
          </div>
          <div className="event-detail">
            <div className="event-detail-label">Источник даты</div>
            <div className="event-detail-value">${row.event_date_source || '—'}${row.event_date_confidence != null ? ` · ${Math.round(Number(row.event_date_confidence || 0) * 100)}%` : ''}</div>
          </div>
        </div>
        <div>
          <div className="event-detail-label" style=${{ marginBottom: '8px' }}>Полное сообщение</div>
          <div className="event-full-text">${row.text || '—'}</div>
        </div>
      <//>
    `;
  }

  function DayEventsPopup({ day, onClose, onOpenEvent }) {
    if (!day || !Array.isArray(day.events)) return null;
    return html`
      <${Modal}
        open=${Boolean(day)}
        onClose=${onClose}
        title=${`События за ${day.title}`}
        subtitle=${`${day.events.length} сообщений-событий. Нажмите на карточку, чтобы прочитать полностью.`}
        ariaLabel="События дня"
        backdropClassName="event-modal-backdrop"
        className="event-modal day-events-modal"
        headerClassName="event-modal-head"
        titleClassName="event-modal-title"
        bodyClassName="event-modal-body"
      >
        <div className="day-events-popup-list">
          ${day.events.map((row, index) => html`
            <button
              className="day-event-card"
              type="button"
              key=${`${row.lead}-${row.message_id}-${index}`}
              onClick=${() => onOpenEvent(row)}
            >
              <div className="day-event-card-head">
                <strong>${row.lead || 'Событие'}</strong>
                <span>${eventAuthor(row)}</span>
              </div>
              <div className="subtle">${formatDateTime(row.date_utc)}${row.event_date ? ` · дата мероприятия: ${row.event_date}` : ''}</div>
              <div className="day-event-card-text">${row.text || '—'}</div>
            </button>
          `)}
        </div>
      <//>
    `;
  }

  function CalendarPage() {
    const [loading, setLoading] = React.useState(false);
    const [calendarLoading, setCalendarLoading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [rows, setRows] = React.useState([]);
    const [calendarRows, setCalendarRows] = React.useState([]);
    const [query, setQuery] = React.useState('');
    const [viewMode, setViewMode] = React.useState('calendar');
    const [visibleMonth, setVisibleMonth] = React.useState(() => monthStart(new Date()));
    const [page, setPage] = React.useState(1);
    const [pageSize, setPageSize] = React.useState(5);
    const [total, setTotal] = React.useState(0);
    const [totalPages, setTotalPages] = React.useState(1);
    const [selectedEvent, setSelectedEvent] = React.useState(null);
    const [selectedDayEvents, setSelectedDayEvents] = React.useState(null);

    const loadRows = React.useCallback(async (nextPage = page, nextPageSize = pageSize) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          page: String(nextPage),
          page_size: String(nextPageSize),
          query: String(query || '').trim(),
        });
        const response = await fetch(`/api/payme/calendar-events?${params.toString()}`, {
          headers: { Accept: 'application/json' },
          cache: 'no-store',
        });
        if (!response.ok) {
          let text = '';
          try { text = await response.text(); } catch (_) {}
          throw new Error(`HTTP ${response.status} ${response.statusText}${text ? ' — ' + text : ''}`);
        }
        const data = await response.json();
        setRows(Array.isArray(data.items) ? data.items : []);
        setTotal(Number(data.total || 0));
        setTotalPages(Math.max(1, Number(data.total_pages || 1)));
        setPage(Number(data.page || nextPage || 1));
        setPageSize(Number(data.page_size || nextPageSize || 5));
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setLoading(false);
      }
    }, [page, pageSize, query]);

    const loadCalendarRows = React.useCallback(async (month = visibleMonth) => {
      setCalendarLoading(true);
      setError(null);
      try {
        const firstDay = toYmd(monthStart(month));
        const lastDay = monthEndYmd(month);
        const collected = [];
        let nextPage = 1;
        let pages = 1;
        do {
          const params = new URLSearchParams({
            page: String(nextPage),
            page_size: '100',
            limit: '50000',
            query: String(query || '').trim(),
            date_from: firstDay,
            date_to: lastDay,
          });
          const response = await fetch(`/api/payme/calendar-events?${params.toString()}`, {
            headers: { Accept: 'application/json' },
            cache: 'no-store',
          });
          if (!response.ok) {
            let text = '';
            try { text = await response.text(); } catch (_) {}
            throw new Error(`HTTP ${response.status} ${response.statusText}${text ? ' — ' + text : ''}`);
          }
          const data = await response.json();
          collected.push(...(Array.isArray(data.items) ? data.items : []));
          pages = Math.max(1, Number(data.total_pages || 1));
          nextPage += 1;
        } while (nextPage <= pages && nextPage <= 20);
        setCalendarRows(collected);
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setCalendarLoading(false);
      }
    }, [visibleMonth, query]);

    const debouncedReload = useDebouncedCallback(() => {
      setPage(1);
      if (viewMode === 'calendar') {
        loadCalendarRows(visibleMonth);
      } else {
        loadRows(1);
      }
    }, 300);

    React.useEffect(() => {
      loadCalendarRows(visibleMonth);
    }, []);

    React.useEffect(() => {
      const timer = window.setInterval(() => {
        if (viewMode === 'calendar') {
          loadCalendarRows(visibleMonth);
        } else {
          loadRows(page);
        }
      }, 15000);
      return () => window.clearInterval(timer);
    }, [loadRows, loadCalendarRows, page, viewMode, visibleMonth]);

    React.useEffect(() => {
      if (viewMode === 'calendar') {
        loadCalendarRows(visibleMonth);
      } else if (!rows.length) {
        loadRows(1);
      }
    }, [viewMode, visibleMonth]);

    React.useEffect(() => {
      if (!selectedEvent && !selectedDayEvents) return undefined;
      const handleKeyDown = (event) => {
        if (event.key === 'Escape') {
          setSelectedEvent(null);
          setSelectedDayEvents(null);
        }
      };
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }, [selectedEvent, selectedDayEvents]);

    const pageWindow = () => {
      const current = Math.min(Math.max(1, page), totalPages);
      let start = Math.max(1, current - 2);
      let end = Math.min(totalPages, start + 4);
      start = Math.max(1, end - 4);
      const pages = [];
      for (let item = start; item <= end; item += 1) pages.push(item);
      return pages;
    };

    const rangeText = () => {
      if (!rows.length || !total) return '0 из 0';
      const start = (page - 1) * pageSize;
      return `${start + 1}-${Math.min(total, start + rows.length)} из ${total}`;
    };

    const goToPage = (nextPage) => {
      const safePage = Math.min(Math.max(1, Number(nextPage || 1)), totalPages);
      setPage(safePage);
      loadRows(safePage);
    };

    const openMonth = (nextMonth) => {
      const normalized = monthStart(nextMonth);
      setVisibleMonth(normalized);
      if (viewMode === 'calendar') {
        loadCalendarRows(normalized);
      }
    };

    const today = new Date();
    const todayYmd = toYmd(today);
    const monthDays = calendarDaysForMonth(visibleMonth);
    const rowsByDate = calendarRows.reduce((acc, row) => {
      const key = String(row.event_date || '').slice(0, 10);
      if (!key) return acc;
      if (!acc[key]) acc[key] = [];
      acc[key].push(row);
      return acc;
    }, {});

    return html`
      <div className="page">
        <${PageHeader}
          title="Календарь"
          subtitle="Даты мероприятий, извлечённые OpenRouter LLM из полного текста сообщений."
          active="calendar"
        />

        <section className="toolbar">
          <div className="toolbar-group">
            <button className=${`btn ${viewMode === 'calendar' ? 'btn-active' : ''}`} onClick=${() => setViewMode('calendar')}>Календарь</button>
            <button className=${`btn ${viewMode === 'table' ? 'btn-active' : ''}`} onClick=${() => setViewMode('table')}>Таблица</button>
            <input
              className="input"
              style=${{ minWidth: '300px' }}
              type="text"
              placeholder="Поиск по каналу, тексту, автору или дате…"
              value=${query}
              onChange=${(event) => { setQuery(event.target.value); debouncedReload(); }}
            />
            ${viewMode === 'table' ? html`
              <select className="select" value=${String(pageSize)} onChange=${(event) => {
                const nextSize = Number(event.target.value);
                setPageSize(nextSize);
                setPage(1);
                loadRows(1, nextSize);
              }}>
                <option value="5">5 строк</option>
                <option value="10">10 строк</option>
                <option value="20">20 строк</option>
                <option value="50">50 строк</option>
              </select>
            ` : null}
            <button
              className="btn"
              onClick=${() => viewMode === 'calendar' ? loadCalendarRows(visibleMonth) : loadRows(page)}
              disabled=${loading || calendarLoading}
            >
              ${loading || calendarLoading ? 'Обновление…' : 'Обновить'}
            </button>
          </div>
          <div className="toolbar-group">
            <span className="badge badge-active">Событий с датой: ${viewMode === 'calendar' ? calendarRows.length : total}</span>
          </div>
        </section>

        ${viewMode === 'calendar' ? html`
          <section className="calendar-shell">
            <div className="calendar-head">
              <div className="calendar-title">
                <strong>${MONTH_NAMES[visibleMonth.getMonth()]}</strong> ${visibleMonth.getFullYear()} г.
              </div>
              <div className="calendar-controls">
                <button className="icon-btn" type="button" onClick=${() => openMonth(addMonths(visibleMonth, -1))}>‹</button>
                <button className="today-btn" type="button" onClick=${() => openMonth(new Date())}>Сегодня</button>
                <button className="icon-btn" type="button" onClick=${() => openMonth(addMonths(visibleMonth, 1))}>›</button>
              </div>
            </div>
            <div className="week-row">
              ${WEEK_DAYS.map((day, index) => html`<div className=${`week-day ${index >= 5 ? 'weekend' : ''}`} key=${day}>${day}</div>`)}
            </div>
            ${calendarLoading && !calendarRows.length ? html`<${LoadingNotice} message="Загружаю календарь…" details="Показываются мероприятия, где LLM уже нашёл дату." />` : null}
            <div className="calendar-grid">
              ${monthDays.map((day) => {
                const dayEvents = rowsByDate[day.ymd] || [];
                const isCrowded = dayEvents.length > 3;
                const visibleEvents = isCrowded ? dayEvents.slice(0, 2) : dayEvents;
                return html`
                  <div className=${`day-cell ${day.isWeekend ? 'weekend' : ''} ${day.inMonth ? '' : 'outside'}`} key=${day.ymd}>
                    <div className=${`day-number ${day.ymd === todayYmd ? 'today' : ''}`}>
                      <span>${dayLabel(day.date)}</span>
                    </div>
                    <div className="day-events">
                      ${visibleEvents.map((row) => html`
                        <button
                          className="calendar-event"
                          type="button"
                          key=${`${row.lead}-${row.message_id}`}
                          onClick=${() => setSelectedEvent(row)}
                          title="Открыть детали события"
                        >
                          <strong>${row.lead}</strong>
                          <span>${(row.text || '—').slice(0, 90)}</span>
                        </button>
                      `)}
                      ${isCrowded ? html`
                        <button
                          className="many-events-btn"
                          type="button"
                          onClick=${() => setSelectedDayEvents({
                            title: `${day.date.getDate()} ${MONTH_NAMES_GENITIVE[day.date.getMonth()]} ${day.date.getFullYear()} г.`,
                            events: dayEvents,
                          })}
                        >
                          много: ${dayEvents.length}
                        </button>
                      ` : null}
                    </div>
                  </div>
                `;
              })}
            </div>
          </section>
        ` : html`
        <section className="panel">
          <div className="table-wrap">
            ${loading && rows.length === 0 ? html`<${LoadingNotice} message="Загружаю календарь…" details="Показываются только мероприятия, для которых LLM уже нашёл дату." />` : null}
            ${!loading && rows.length === 0 ? html`<div className="empty">Даты мероприятий пока не найдены. Откройте “Мероприятия”, чтобы backend начал LLM-разбор видимых сообщений.</div>` : null}
            ${rows.length ? html`
              <table>
                <thead>
                  <tr>
                    <th>Дата мероприятия</th>
                    <th>Канал</th>
                    <th>Сообщение</th>
                    <th>Автор</th>
                    <th>Дата сообщения</th>
                  </tr>
                </thead>
                <tbody>
                  ${rows.map((row) => html`
                    <tr key=${`${row.lead}-${row.message_id}`}>
                      <td><strong>${row.event_date || '—'}</strong></td>
                      <td>
                        <div><strong>${row.lead}</strong></div>
                        <div className="subtle">${row.source_selector || '—'}</div>
                      </td>
                      <td><div className="message-text">${row.text || '—'}</div></td>
                      <td>${eventAuthor(row)}</td>
                      <td>${window.fmtDate ? window.fmtDate(row.date_utc, true) : (row.date_utc || '—')}</td>
                    </tr>
                  `)}
                </tbody>
              </table>
            ` : null}
          </div>
          <${TablePaginationFooter}
            rangeText=${rangeText()}
            page=${page}
            totalPages=${totalPages}
            pageWindow=${pageWindow()}
            onPrev=${() => goToPage(page - 1)}
            onNext=${() => goToPage(page + 1)}
            onGo=${goToPage}
            paginationClassName="nav"
          />
        </section>
        `}

        <${ErrorBox} error=${error} />
        <${DayEventsPopup}
          day=${selectedDayEvents}
          onClose=${() => setSelectedDayEvents(null)}
          onOpenEvent=${(row) => {
            setSelectedDayEvents(null);
            setSelectedEvent(row);
          }}
        />
        <${EventPopup} row=${selectedEvent} onClose=${() => setSelectedEvent(null)} />
      </div>
    `;
  }

  function mount() {
    const rootNode = document.getElementById('app');
    if (!rootNode) return;
    ReactDOM.createRoot(rootNode).render(html`<${CalendarPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();

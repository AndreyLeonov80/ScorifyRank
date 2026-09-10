/* Shared deals runtime utilities */
'use strict';

(function initReactDealsUtils() {
  window.BackfrontDealsUtils = function BackfrontDealsUtils() {
  const API_BASE = window.API_BASE || '';

  const STAGES = [
    ['idea', 'Идея'],
    ['lead', 'Лид'],
    ['qualified', 'Квалифицирован'],
    ['proposal', 'КП'],
    ['negotiation', 'Переговоры'],
    ['contract', 'Договор'],
    ['won', 'Выиграна'],
    ['lost', 'Потеряна'],
  ];

  const LEAD_TEMPERATURES = [
    ['all', 'Все лиды'],
    ['hot', 'Горячие'],
    ['warm', 'Тёплые'],
    ['cold', 'Холодные'],
    ['not_fit', 'Не подходит'],
    ['needs_data', 'Нужно больше данных'],
  ];

  const CONTRACT_STATUSES = [
    ['needs_data', 'нужны данные'],
    ['proposal_ready', 'КП готово'],
    ['sent', 'отправлено'],
    ['negotiation', 'на согласовании'],
    ['signed', 'подписано'],
    ['paid', 'оплачено'],
  ];

  const fmtMoney = (value) => {
    const number = Number(value || 0);
    return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(number);
  };

  const fmtDate = (value) => {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString('ru-RU');
  };

  const slaLabel = (status) => ({
    red: 'просрочено',
    yellow: 'скоро',
    green: 'в норме',
    done: 'закрыта',
  }[status] || 'в норме');

  const slaClass = (status) => ({
    red: 'sla-red',
    yellow: 'sla-yellow',
    green: 'sla-green',
    done: 'sla-done',
  }[status] || 'sla-green');

  const stageLabel = (stage) => {
    const item = STAGES.find(([value]) => value === stage);
    return item ? item[1] : stage || 'Стадия';
  };

  const kanbanCardClass = (row) => {
    if ((row.stage || '') === 'won' || (row.stage || '') === 'lost') return 'kanban-card kanban-card-done';
    if ((row.sla_status || '') === 'red') return 'kanban-card kanban-card-red';
    if ((row.sla_status || '') === 'yellow') return 'kanban-card kanban-card-yellow';
    return 'kanban-card';
  };

  const auditActionLabel = (action) => ({
    create: 'создана',
    update: 'обновлена',
    delete: 'удалена',
    create_from_enreach: 'создана из enReach',
    contract_status: 'статус договора',
  }[action] || action || 'действие');

  const auditChangesText = (changes) => {
    const entries = Object.entries(changes || {}).filter(([, value]) => value != null && value !== '');
    if (!entries.length) return '—';
    return entries.map(([key, value]) => `${key}: ${value}`).join(' · ');
  };

  const contractStatusLabel = (status) => {
    const item = CONTRACT_STATUSES.find(([value]) => value === status);
    return item ? item[1] : status || 'нужны данные';
  };

  function downloadTextFile(filename, text) {
    const blob = new Blob([String(text || '')], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function apiJson(url, options = {}) {
    if (window.BackfrontApi?.apiJson) {
      return window.BackfrontApi.apiJson(url, options);
    }

    const response = await fetch(url, {
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) },
      cache: 'no-store',
      ...options,
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) {
      throw new Error(data?.detail || data?.message || `HTTP ${response.status}`);
    }
    return data;
  }

    return {
      API_BASE,
      STAGES,
      LEAD_TEMPERATURES,
      CONTRACT_STATUSES,
      fmtMoney,
      fmtDate,
      slaLabel,
      slaClass,
      stageLabel,
      kanbanCardClass,
      auditActionLabel,
      auditChangesText,
      contractStatusLabel,
      downloadTextFile,
      apiJson,
    };
  };
})();

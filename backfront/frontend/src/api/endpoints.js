import { apiJson } from './client.js';

export const serverStatus = () => apiJson('/api/payme/server-status');
export const runtimeStatus = () => apiJson('/api/payme/runtime-status');
export const dashboardSummary = (limit = 5) => apiJson(`/api/payme/dashboard/summary?limit=${limit}`);
export const importDialogs = (params = '') => apiJson(`/api/payme/import/dialogs${params}`);
export const leads = (params = '') => apiJson(`/api/payme/leads${params}`);
export const settings = () => apiJson('/api/payme/settings');
export const systemMetrics = (params = '') => apiJson(`/api/payme/system-metrics${params}`);
export const runtimeLogs = (params = '') => apiJson(`/api/payme/runtime-logs${params}`);
export const licenseStatus = () => apiJson('/api/payme/license/status');
export const licenseMenus = () => apiJson('/api/payme/license/menus');
export const contacts = (params = '') => apiJson(`/api/payme/contacts${params}`);
export const crmContacts = (params = '') => apiJson(`/api/payme/crm/contacts${params}`);
export const mediaStatus = () => apiJson('/api/payme/media/status');
export const eventsStatus = () => apiJson('/api/payme/events/status');
export const importSyncStatus = () => apiJson('/api/payme/import-sync/status');

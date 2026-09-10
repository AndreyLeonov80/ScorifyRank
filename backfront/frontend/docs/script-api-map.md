# script.api.js Map

## HTML/JS references
calendar.html:13:  <script src="js/script.api.js?v=20260521-css-api"></script>
contacts.html:14:  <script src="js/script.api.js?v=20260521-css-api"></script>
crm.html:14:  <script src="js/script.api.js?v=20260521-css-api"></script>
events.html:14:  <script src="js/script.api.js?v=20260521-css-api"></script>
grid.html:14:  <script src="js/script.api.js?v=20260521-css-api"></script>
import.html:14:  <script src="js/script.api.js?v=20260521-css-api"></script>
index.html:19:  <script src="js/script.api.js?v=20260521-css-api"></script>
jur-entities.html:14:  <script src="js/script.api.js?v=20260521-css-api"></script>
media.html:14:  <script src="js/script.api.js?v=20260521-css-api"></script>
outreach.html:12:  <script src="js/script.api.js?v=20260521-css-api"></script>
routes.html:12:  <script src="js/script.api.js?v=20260521-css-api"></script>
js/script.api.js:1:/* script.api.js v4 - FIXED */

`js/old-script.api.js` is not present in the active frontend tree and is archived under `gramlead-main-new-optimize-arxived-ext123/backfront-ext-rd-codes/js/old-script.api.js`.

## Global page factories and exported functions
4:function initApp() {
110:  window.fmtDate = fmtDate;
120:  window.confirmLongRebuild = confirmLongRebuild;
233:    if (typeof window.structuredClone === 'function') {
1185:  window.BackfrontActions = window.BackfrontActions || {};
1216:  window.BackfrontClearRuntimeState = clearFrontendRuntimeState;
1294:  window.leadApp = function leadApp() {
2653:  window.gridApp = function gridApp() {
3230:  window.contactsApp = function contactsApp() {
4186:  window.crmApp = function crmApp() {
4774:  window.outreachApp = function outreachApp() {
4926:  window.mediaApp = function mediaApp() {
5790:  window.imagesApp = window.mediaApp;
5792:  window.eventsApp = function eventsApp() {
6272:  window.telegramImportApp = function telegramImportApp() {
6852:  window.jurEntitiesApp = function jurEntitiesApp() {
7086:  window.addLlmButton = function(label, optDataText) {
## Split status

- `src/api/client.js` добавлен как новый единый API-клиент.
- `src/api/endpoints.js` добавлен как первый слой именованных endpoint-функций.
- `src/shared/format.js` добавлен как место для общих форматтеров.
- `js/api.client.js` добавлен как браузерный API transport-layer для legacy HTML и React-страниц.
- `js/debug.client.js` отделяет debug-логирование от page-store логики; подробные `console.log` включаются только через `XFILES_DEBUG` / `BACKFRONT_DEBUG` / `localStorage.backfront.debug`.
- `js/legacy.actions.js` отделяет общие legacy-действия меню (`BackfrontActions`, `BackfrontClearRuntimeState`) от монолитного `script.api.js`.
- `js/status.panel.js` добавлен как shared renderer для статус-панелей legacy stores и React-страниц.
- `BackfrontReactShared.StatusPanel` подключён на Contacts / CRM / Media / Events: статусные панели теперь получают config из legacy store, а UI-render живёт в общем React/shared слое.
- `scripts/audit-script-api.mjs` добавлен как повторяемая проверка: HTML-подключения, global factories, endpoint constants, API helpers и прямые `console.log`.
- Рабочие HTML всё ещё могут использовать `js/script.api.js` как совместимый page-store слой, но API-запросы делегируются в общий `BackfrontApi`, если он загружен.

## Safe migration order

1. Держать `js/api.client.js` подключенным перед `js/script.api.js` и React-страницами.
2. Переносить endpoint-функции из `script.api.js` в `src/api/endpoints.js` и `BackfrontApi.endpoints` небольшими группами.
3. Debug/legacy-функции удалять из `script.api.js` только после `rg`-проверки подключений.
4. `js/script.api.js` уменьшать частями: API -> formatters -> UI helpers -> page modules.

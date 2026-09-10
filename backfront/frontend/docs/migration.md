# Frontend Migration Notes

- Do not delete a page until its route and license visibility are verified.
- Move shared CSS first.
- Then split `script.api.js` into API and page controllers.
- 2026-05-21: API transport separated into `js/api.client.js`; React pages and `script.api.js` now delegate JSON requests to `window.BackfrontApi` when it is loaded.
- 2026-05-21: Debug logging moved behind `js/debug.client.js`; legacy menu actions moved into `js/legacy.actions.js` for pages that do not load the monolithic store.
- 2026-05-21: Shared status-panel UI moved into `js/status.panel.js` and `BackfrontReactShared.StatusPanel`; Contacts/CRM/Media/Events now render those panels through the shared React component.
- Then migrate screens to React one by one.
- Keep public HTML filenames stable during migration.

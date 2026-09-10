# Frontend Architecture

Current imported shape:

- Single top-level `app.html` shell with route/page metadata in `app.manifest.json`.
- Shared `js/api.client.js` transport layer plus compatibility `js/script.api.js` page stores where needed.
- Shared React layout/navigation/status/loading/pagination components in `js/react.shared.js`.
- Shared `css/style.css` covers common primitives; page-specific CSS lives in `css/pages/*.css`.

Target shape:

- one app shell;
- shared layout/header/menu components;
- shared table/filter/pagination components;
- one API client layer;
- feature pages loaded lazily;
- no duplicated inline CSS in production pages.

See `docs/component-audit.md` for the current shell/component status and the remaining migration gaps.

Production static delivery:

- `npm run build` writes minified HTML/CSS and copied runtime JS to `dist`;
- the build produces one `dist/index.html` plus `app.manifest.json` for 18 route-compatible page names;
- `app.entry.js` creates the page root and delegates bundle loading to `react.page-loader.js`;
- the frontend Docker image builds `dist` in a Node stage and serves it from nginx.

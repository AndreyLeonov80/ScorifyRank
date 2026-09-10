# Component Audit

## Active App Shell

`app.html` is the only active HTML entrypoint. It creates the page root from `app.manifest.json`, loads `css/pages/*.css`, and then lazy-loads the matching React bundle through `js/react.page-loader.js`.

The manifest keeps the 18 route-compatible page names:

- calendar.html
- contacts.html
- crm.html
- dashboard.html
- deals.html
- events.html
- grid.html
- import.html
- index.html
- jur-entities.html
- logs.html
- media.html
- needs.html
- outreach.html
- routes.html
- settings.html
- setup_wizard.html
- tariffs.html

`rg "x-data|@click|onclick=|onchange=|onsubmit=" backfront/frontend/app.html` returns no matches, so the active HTML shell no longer contains Alpine or inline event handlers.

## Shared React Components In Use

- `PageHeader`, `PageNav`, `ApiBaseBadge`: shared layout/header/navigation.
- `Pagination`, `TablePaginationFooter`: shared pagination footer controls.
- `DataTable`: shared table renderer, first migrated on `needs.html`.
- `FormGrid`, `FormField`: shared form layout primitives, first migrated on `needs.html`.
- `Modal`: shared dialog shell, first migrated on `calendar.html`.
- `StatusPanel`: shared status-panel renderer bridge.
- `ErrorBox`, `LoadingNotice`, `TelegramCooldownBanner`: shared feedback/loading states.
- `OutreachToggle`, `DealActionButton`: shared action controls across table-heavy pages.
- `app.entry.js`: single-entrypoint router that mounts the manifest-selected React root.
- `react.page-loader.js`: shared lazy loader for per-page React bundles declared through the manifest.

## Remaining Work

- Broaden `DataTable`, `FormGrid`, `FormField`, and `Modal` usage across the remaining page-local markup.

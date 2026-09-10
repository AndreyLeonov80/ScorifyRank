# CSS Audit

## Page CSS Files

После перехода на один HTML entrypoint бывшие inline `<style>` блоки страниц вынесены в `css/pages/*.css`.

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

## Current shared CSS size
     191 css/style.css

## Shared CSS baseline

- `css/style.css` создан и подключен к единственному `app.html`.
- `css/pages/*.css` подключаются динамически из `app.manifest.json` для 18 route-compatible страниц.
- В общий CSS вынесены повторяющиеся правила для `.subtle`, `.btn:hover`, `.btn:disabled`, `.btn-active`, статусных `.badge-*`, `.pagination` и `box-sizing`.
- Из бывших HTML shell-ов удалено 96 точных дублей. В `css/pages/*.css` оставлены только уникальные или намеренно отличающиеся правила страниц.
- Оставшиеся похожие правила не удалялись автоматически: они отличаются набором свойств (`line-height`, `select:hover`, особая pagination calendar, упрощенные badge на index).

## Active page CSS files

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

# Frontend API Usage

The current frontend uses `js/script.api.js` for the main API calls and page controllers.

The first safe split is:

- `src/api/client.js` - `fetch` wrapper, errors, timeout, base URL.
- `src/api/endpoints.js` - endpoint constants.
- `src/api/*.js` - feature-specific API calls.
- `src/pages/*` - UI/page logic.

